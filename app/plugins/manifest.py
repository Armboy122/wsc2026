"""สัญญาของ plugin manifest ที่ตรวจสอบกับ Pydantic contracts จริงเสมอ

manifest เป็น trusted configuration ที่ commit อยู่ใน repository ทำหน้าที่เพียง
discovery และ metadata ส่วน schema ของ input/output ยังคงมาจาก ``app/contracts.py``
เพื่อไม่ให้เกิด schema สองชุดที่ drift ออกจากกัน
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts import (
    INPUT_MODELS,
    OUTPUT_MODELS,
    PREPARE_TO_SUBMIT,
    TOOL_ACTIONS,
    ToolAction,
    ToolName,
)

# factory ต้องอยู่ใต้แพ็กเกจปลั๊กอินของ repository เท่านั้น ไม่รับ path จากภายนอก
TRUSTED_FACTORY_ROOT = "app.plugins."


class OperationExposure(str, Enum):
    """ระบุว่าใครเรียก operation นี้ได้"""

    LLM = "llm"
    INTERNAL = "internal"


class OperationMode(str, Enum):
    """ระบุบทบาทของ operation ใน write state machine"""

    READ = "read"
    PREPARE = "prepare"
    SUBMIT = "submit"


class PluginOperation(BaseModel):
    """หนึ่ง operation ที่ปลั๊กอินประกาศไว้ใน manifest"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ToolAction
    description: str = Field(min_length=1, max_length=1000)
    exposure: OperationExposure
    mode: OperationMode
    submit_action: ToolAction | None = Field(default=None, alias="submitAction")
    input_contract: str = Field(min_length=1, alias="inputContract")
    output_contract: str = Field(min_length=1, alias="outputContract")

    @model_validator(mode="after")
    def _check_contracts(self) -> PluginOperation:
        """ยึด Pydantic contracts เป็น source of truth และ fail closed เมื่อ manifest drift"""
        expected_input = INPUT_MODELS[self.action].__name__
        if self.input_contract != expected_input:
            raise ValueError(
                f"inputContract ของ {self.action.value} ต้องเป็น {expected_input} ไม่ใช่ {self.input_contract}"
            )
        expected_output = OUTPUT_MODELS[self.action].__name__
        if self.output_contract != expected_output:
            raise ValueError(
                f"outputContract ของ {self.action.value} ต้องเป็น {expected_output} ไม่ใช่ {self.output_contract}"
            )
        expected_submit = PREPARE_TO_SUBMIT.get(self.action)
        if self.mode is OperationMode.PREPARE:
            if expected_submit is None:
                raise ValueError(f"{self.action.value} ไม่ใช่ prepare action ตามสัญญา")
            if self.submit_action is not expected_submit:
                raise ValueError(
                    f"submitAction ของ {self.action.value} ต้องเป็น {expected_submit.value}"
                )
        elif self.submit_action is not None:
            raise ValueError(f"{self.action.value} ต้องไม่ประกาศ submitAction")
        # รายการเขียนต้องผ่านการยืนยันจากมนุษย์เสมอ จึงห้ามเปิดให้ LLM เรียกเอง
        if self.mode is OperationMode.SUBMIT and self.exposure is not OperationExposure.INTERNAL:
            raise ValueError(f"submit action ต้องเป็น internal เท่านั้น: {self.action.value}")
        return self


class PluginConfiguration(BaseModel):
    """ชื่อ environment variable ที่ปลั๊กอินใช้ (ไม่เก็บค่า secret ใน manifest)"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url_env: str | None = Field(default=None, alias="baseUrlEnv")
    timeout_env: str | None = Field(default=None, alias="timeoutEnv")
    api_key_env: str | None = Field(default=None, alias="apiKeyEnv")


class PluginMetadata(BaseModel):
    """ข้อมูลระบุตัวตนของปลั๊กอิน"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ToolName
    name: str = Field(min_length=1, max_length=200)
    enabled: bool
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)


class PluginRuntime(BaseModel):
    """ตำแหน่ง factory ที่ loader จะ import"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    factory: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_trusted_path(self) -> PluginRuntime:
        module, separator, attribute = self.factory.partition(":")
        if not separator or not attribute:
            raise ValueError("factory ต้องอยู่ในรูปแบบ 'module:callable'")
        if not module.startswith(TRUSTED_FACTORY_ROOT):
            raise ValueError(f"factory ต้องอยู่ใต้ {TRUSTED_FACTORY_ROOT}")
        return self


class PluginManifest(BaseModel):
    """manifest หนึ่งไฟล์ที่ผ่านการตรวจสอบครบแล้ว"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_version: str = Field(alias="apiVersion")
    kind: str
    metadata: PluginMetadata
    runtime: PluginRuntime
    configuration: PluginConfiguration = Field(default_factory=PluginConfiguration)
    operations: tuple[PluginOperation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_manifest(self) -> PluginManifest:
        if self.api_version != "pea.one/v1":
            raise ValueError(f"ไม่รองรับ apiVersion: {self.api_version}")
        if self.kind != "Plugin":
            raise ValueError(f"ไม่รองรับ kind: {self.kind}")
        actions = [operation.action for operation in self.operations]
        if len(set(actions)) != len(actions):
            raise ValueError("ประกาศ action ซ้ำใน manifest เดียวกัน")
        allowed = TOOL_ACTIONS[self.metadata.id]
        unknown = {action.value for action in actions} - {action.value for action in allowed}
        if unknown:
            raise ValueError(f"action ไม่ตรงกับเครื่องมือ {self.metadata.id.value}: {sorted(unknown)}")
        # เครื่องมือต้องประกาศ action ครบตามสัญญา ไม่เช่นนั้น registry จะรับ call ที่ manifest ไม่รู้จัก
        missing = {action.value for action in allowed} - {action.value for action in actions}
        if missing:
            raise ValueError(f"manifest ขาด action ตามสัญญา: {sorted(missing)}")
        return self

    @property
    def llm_actions(self) -> tuple[PluginOperation, ...]:
        """เฉพาะ operation ที่เปิดให้ LLM เห็นในแคตตาล็อก"""
        return tuple(
            operation
            for operation in self.operations
            if operation.exposure is OperationExposure.LLM
        )
