"""ปลั๊กอิน VOC ที่โหลดจริงผ่านสามชั้นสาธารณะ: MainAgent · VoiceBridge · ToolAdminService

ความเสี่ยงที่เทสนี้กันไว้ (docs/v2/TASKS.md T5.3 — ``ChoicePrompt`` ต้องข้าม channel ได้):

- เดิน flow จริงตั้งแต่ ``load_plugins`` ตามการประกอบของ production (app/main.py) —
  VocTool จริงคุยกับ gateway ผ่าน HTTP จริง โดย fake อยู่เฉพาะขอบเขต HTTP ของ catalog
- MainAgent: เริ่ม VOC ได้ ``ChoicePrompt`` และเทิร์นถัดไปด้วย
  ``selectedPromptId``/``selectedValue`` เดิน flow จริงต่อในบทสนทนาเดิม
- VoiceBridge (has_display=False): guidance ต้องมีตัวเลือกครบทุกข้อ และป้ายที่พูด
  (label) ต้องเดิน flow เดิมต่อได้บน conversation เดียวกัน
- ToolAdminService: voc_tool ที่โหลดจริงต้องแสดงเป็น code tool ที่แก้ไม่ได้
  พร้อม operation ตาม manifest จริง

ไม่ซ้ำกับเทสเดิม: prepare/confirm/submit/idempotency (app/tools/tests/test_voc_tool.py),
backend จำลอง (app/backends/tests/test_simulated_voc.py), flow unit (app/plugins/tests/),
bridge กับ fake gateway (app/live/tests/test_bridge.py), และรายการ admin ที่ไม่มีปลั๊กอิน
(tests/test_admin_tool_list.py)
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

import pytest

from app.agent.guided_flow import GuidedFlows
from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import GroundedEvidence
from app.contracts import ChatRequest
from app.core.config import Settings
from app.core.tool_admin import ToolAdminService
from app.db import Database
from app.llm import LLMClient, ScriptedLLMAdapter
from app.live.bridge import VoiceBridge
from app.plugins import load_plugins
from app.plugins.loader import LoadedPlugin
from app.tools.knowledge_tool import KnowledgeTool

# ขั้นแรกของ intake ที่ปลั๊กอินถามจริง (app/plugins/voc/intake.py)
_FIRST_PROMPT_ID = "voc_journey"
# ตัวเลือก journey มาจาก catalog ของ gateway จริงตามลำดับที่ประกาศ
_JOURNEY_LABELS = {"แจ้งปัญหาด้านบริการ", "แจ้งเบาะแส"}
_CASE_OPENING_MESSAGE = "ร้องเรียนบริการหน่อยครับ"


def _integration_catalog() -> dict[str, object]:
    """Minimal catalog fixture at the HTTP boundary; the production parser stays exercised."""
    return {
        "catalogVersion": "P3-INTEGRATION-1",
        "journeys": [
            {
                "code": "SERVICE_ISSUE",
                "label": "แจ้งปัญหาด้านบริการ",
                "reporterMode": "OPTIONAL",
                "classificationRootCodes": ["REQUEST_1"],
                "requiresIncidentLocation": False,
            },
            {
                "code": "TIP_OFF",
                "label": "แจ้งเบาะแส",
                "reporterMode": "OPTIONAL",
                "classificationRootCodes": ["REQUEST_4"],
                "requiresIncidentLocation": False,
            },
        ],
        "requestTypes": [
            {
                "code": "REQUEST_1",
                "name": "ร้องเรียน",
                "topics": [{
                    "code": "SERVICE",
                    "name": "การให้บริการ",
                    "issues": [{"code": "SERVICE_DELAY", "name": "บริการล่าช้า", "subIssues": []}],
                }],
            },
            {
                "code": "REQUEST_4",
                "name": "แจ้งเบาะแส",
                "topics": [{
                    "code": "SAFETY",
                    "name": "ความปลอดภัย",
                    "issues": [{"code": "SUSPICIOUS_ACTIVITY", "name": "พบความผิดปกติ", "subIssues": []}],
                }],
            },
        ],
    }


class _MinimalKnowledgeBackend:
    """backend ปลอมขั้นต่ำ — KnowledgeTool จริงเรียก ``search`` ตาม protocol"""

    async def search(self, query: str, max_results: int) -> GroundedEvidence:
        return GroundedEvidence(
            answer_context="ข้อความฉบับเต็มของเอกสารที่เลือก (ข้อมูลทดสอบ)",
            result_count=1,
            citations=(),
        )


class _FakeVocGatewayHandler(BaseHTTPRequestHandler):
    """ขอบเขต HTTP เดียวที่ปลอม: GET catalog ของ gateway VOC — รูปเดียวกับ gateway จริง"""

    def do_GET(self) -> None:  # noqa: N802 — ชื่อตายตัวของ http.server
        if self.path.endswith("/catalog"):
            payload = json.dumps(_integration_catalog(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture()
def voc_base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeVocGatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/api/v1/voc"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@dataclass(frozen=True)
class _VocStack:
    """ส่วนประกอบที่ประกอบแบบเดียวกับ app/main.py แต่มีเฉพาะปลั๊กอินที่เปิดจริง"""

    agent: MainAgent
    plugins: tuple[LoadedPlugin, ...]
    registry: ToolRegistry
    settings: Settings


@pytest.fixture()
def voc_stack(voc_base_url: str) -> Iterator[_VocStack]:
    settings = Settings.from_env(
        {"APP_ENV": "development", "ADMIN_PASSWORD": "pw", "VOC_BASE_URL": voc_base_url}
    )
    plugins = load_plugins(settings)
    try:
        assert [plugin.manifest.metadata.id.value for plugin in plugins] == ["voc_tool"]
        registry = ToolRegistry(
            [KnowledgeTool(_MinimalKnowledgeBackend()), *(plugin.tool for plugin in plugins)],
            catalogue=tuple(plugin.tool_definition for plugin in plugins),
            response_policies=tuple(
                policy for plugin in plugins if (policy := plugin.response_policy) is not None
            ),
            operation_specs={
                key: spec for plugin in plugins for key, spec in plugin.operation_specs.items()
            },
        )
        guided_flows = GuidedFlows(
            tuple(flow for plugin in plugins if (flow := plugin.guided_flow) is not None)
        )
        agent = MainAgent(LLMClient(ScriptedLLMAdapter()), registry, guided_flows=guided_flows)
        yield _VocStack(agent=agent, plugins=plugins, registry=registry, settings=settings)
    finally:
        for plugin in plugins:
            close = getattr(plugin.tool, "close", None)
            if callable(close):
                close()


async def test_chat_starts_voc_with_choice_prompt_and_selection_advances_the_flow(
    voc_stack: _VocStack,
) -> None:
    """เริ่มเรื่องผ่าน ChatRequest จริง → ChoicePrompt · กดเลือก → flow เดินต่อในบทสนทนาเดิม"""
    first = await voc_stack.agent.handle_chat(ChatRequest(message=_CASE_OPENING_MESSAGE))

    prompt = first.choice_prompt
    assert prompt is not None
    assert prompt.prompt_id == _FIRST_PROMPT_ID
    assert {option.label for option in prompt.options} == _JOURNEY_LABELS

    selected = prompt.options[0]
    second = await voc_stack.agent.handle_chat(
        ChatRequest(
            conversation_id=first.conversation_id,
            message=selected.label,
            selected_prompt_id=prompt.prompt_id,
            selected_value=selected.value,
        )
    )

    assert second.conversation_id == first.conversation_id
    assert second.choice_prompt is not None
    assert second.choice_prompt.prompt_id != prompt.prompt_id


async def test_voice_bridge_without_display_reads_all_options_and_spoken_label_advances(
    voc_stack: _VocStack,
) -> None:
    """ช่องทางไม่มีจอ: guidance ต้องมีตัวเลือกครบ และป้ายที่พูดเดิน flow เดิมต่อได้"""
    bridge = VoiceBridge(voc_stack.agent, has_display=False)

    first = await bridge.handle_text(_CASE_OPENING_MESSAGE)
    prompt = first["choicePrompt"]
    guidance = first["voiceGuidance"]
    assert prompt is not None
    assert guidance is not None
    for option in prompt["options"]:
        assert option["label"] in guidance

    spoken_label = prompt["options"][0]["label"]
    second = await bridge.handle_text(spoken_label)

    assert second["conversationId"] == first["conversationId"]
    second_prompt = second["choicePrompt"]
    assert second_prompt is not None
    assert second_prompt["promptId"] != prompt["promptId"]


async def test_admin_lists_loaded_voc_plugin_as_locked_code_tool_with_real_operations(
    voc_stack: _VocStack,
) -> None:
    """voc_tool ที่โหลดจริงต้องเป็น code tool ที่แก้ไม่ได้ พร้อม operation ตาม manifest จริง"""
    db = Database(":memory:")
    try:
        db.migrate()
        service = ToolAdminService(
            db,
            settings=voc_stack.settings,
            registry=voc_stack.registry,
            plugins=voc_stack.plugins,
        )

        listing = await service.list_tools()
        voc = next(tool for tool in listing["tools"] if tool["slug"] == "voc_tool")

        assert voc["source"] == "code"
        assert voc["enabled"] is True
        assert voc["editable"] is False
        operations = {operation["action"]: operation for operation in voc["operations"]}
        assert set(operations) == {"list_categories", "prepare_case", "submit_case", "get_case"}
        prepare = operations["prepare_case"]
        assert prepare["policy"] == "write_confirm"
        assert prepare["mode"] == "prepare"
        assert prepare["submitAction"] == "submit_case"
        assert operations["submit_case"]["exposure"] == "internal"
    finally:
        db.close()
