from __future__ import annotations

from pydantic import ValidationError
from .contracts import DomainError, Principal, ReadPlugin


class Registry:
    """สัญญา read plugin; ไม่มีบริการรายตัวหรือ write workflow ใน core"""

    def __init__(self, plugins: list[ReadPlugin]):
        self.plugins = {}
        for plugin in plugins:
            if plugin.id in self.plugins:
                raise ValueError("plugin id ซ้ำ")
            self.plugins[plugin.id] = plugin

    def catalogue(self, principal: Principal):
        return [{"id": p.id, "description": p.description,
                 "input_schema": p.input_model.model_json_schema()}
                for p in self.plugins.values() if p.scope in principal.scopes]

    async def invoke(self, key: str, data: dict, principal: Principal):
        plugin = self.plugins.get(key)
        if plugin is None:
            raise DomainError("not_found", "ไม่พบปลั๊กอิน", 404)
        if plugin.scope not in principal.scopes:
            raise DomainError("forbidden", "ไม่มีสิทธิ์ใช้ปลั๊กอิน", 403)
        try:
            value = plugin.input_model.model_validate(data)
        except ValidationError as e:
            raise DomainError("invalid_input", "ข้อมูลนำเข้าไม่ตรงกับสัญญา") from e
        result = await plugin.execute(value)
        try:
            return plugin.output_model.model_validate(result.model_dump())
        except (ValidationError, AttributeError) as e:
            raise DomainError("invalid_result", "ผลลัพธ์ไม่ตรงกับสัญญา", 502) from e
