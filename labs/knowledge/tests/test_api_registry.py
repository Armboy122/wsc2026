import pytest
from fastapi.testclient import TestClient
from voice_assistant.api import create_app
from voice_assistant.contracts import DomainError, Model, Principal
from voice_assistant.registry import Registry


def test_api_auth_owner_and_no_integrations(settings):
    with TestClient(create_app(settings)) as client:
        assert client.post("/ask", json={"question":"ไฟฟ้า"}).status_code == 401
        auth = {"Authorization":"Bearer " + "a"*32}
        plugins = client.get("/plugins", headers=auth).json()
        assert [p["id"] for p in plugins] == ["knowledge.search"]
        response = client.post("/ask", headers=auth, json={"question":"ขอใช้ไฟฟ้าใหม่"})
        assert response.status_code == 200
        assert response.json()["status"] == "evidence_only"
        foreign = client.post("/ask", headers={"Authorization":"Bearer " + "b"*32},
            json={"question":"แล้วใช้อะไร", "session_id":response.json()["session_id"]})
        assert foreign.status_code == 404
        assert client.post("/oms").status_code == 404


class Value(Model):
    value: int


class ExtraPlugin:
    id = "example.read"
    description = "ปลั๊กอินทดสอบสัญญา"
    scope = "example:read"
    input_model = output_model = Value
    async def execute(self, value):
        return Value(value=value.value + 1)


async def test_new_read_plugin_without_changing_core():
    registry = Registry([ExtraPlugin()])
    user = Principal(id="a", scopes={"example:read"})
    assert (await registry.invoke("example.read", {"value":2}, user)).value == 3
    with pytest.raises(DomainError):
        await registry.invoke("example.read", {"unknown":2}, user)
    with pytest.raises(DomainError) as e:
        await registry.invoke("example.read", {"value":2}, Principal(id="b", scopes=set()))
    assert e.value.status == 403
