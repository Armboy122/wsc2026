import asyncio

import pytest
from voice_assistant.bootstrap import authenticate
from voice_assistant.contracts import DraftAnswer, Statement, DomainError
from voice_assistant.sessions import Sessions


async def test_session_survives_restart_and_encrypted(service, settings):
    user = authenticate(settings, "a"*32)
    answer = await service.ask(user, "ขอใช้ไฟฟ้าใหม่ต้องเตรียมอะไร")
    assert answer.status == "evidence_only"
    assert answer.citations
    store = Sessions(settings.database, settings.state_key)
    sid, revision, data = await store.load(user.id, answer.session_id)
    assert data["history"][0]["text"] == "ขอใช้ไฟฟ้าใหม่ต้องเตรียมอะไร"
    assert "บัตรประชาชน".encode() not in settings.database.read_bytes()
    with pytest.raises(DomainError) as error:
        await store.load("bob", sid)
    assert error.value.status == 404


async def test_concurrent_session_commit_rejects_stale_revision(service):
    sid, revision, data = await service.sessions.load("alice", None)
    results = await asyncio.gather(service.sessions.save("alice", sid, revision, data),
        service.sessions.save("alice", sid, revision, data), return_exceptions=True)
    assert sum(isinstance(r, DomainError) for r in results) == 1


class FakeProvider:
    name = "test"
    def __init__(self, forged=False, unavailable=False):
        self.forged, self.unavailable = forged, unavailable
        self.requests = []
    async def answer(self, question, history, evidence):
        self.requests.append((question, history, evidence))
        if self.unavailable:
            raise RuntimeError("sensitive backend error")
        quote = "ไม่มีข้อความนี้ในเอกสารเลย" if self.forged else evidence[0].text.split("\n\n")[1]
        return DraftAnswer(status="answered", statements=(Statement(text="ข้อความตัวอย่าง", source_id=evidence[0].source_id, quote=quote),))
    async def close(self):
        pass


async def test_grounded_multiturn_passes_validated_history(service, settings):
    provider = FakeProvider()
    service.provider = provider
    user = authenticate(settings, "a"*32)
    first = await service.ask(user, "ขอใช้ไฟฟ้าใหม่")
    second = await service.ask(user, "แล้วต้องใช้อะไรอีก", first.session_id)
    assert first.status == second.status == "answered"
    assert provider.requests[1][1][0]["text"] == "ขอใช้ไฟฟ้าใหม่"
    assert second.publication == first.publication


@pytest.mark.parametrize("forged,unavailable,status", [(True,False,"invalid_evidence"),(False,True,"unavailable")])
async def test_invalid_or_unavailable_never_becomes_history(service, settings, forged, unavailable, status):
    service.provider = FakeProvider(forged, unavailable)
    answer = await service.ask(authenticate(settings, "a"*32), "ขอใช้ไฟฟ้าใหม่")
    assert answer.status == status
    assert not answer.citations
    assert "sensitive" not in answer.message
    _, _, data = await service.sessions.load("alice", answer.session_id)
    assert data["history"] == []


async def test_delete_and_expiry(service):
    sid, _, _ = await service.sessions.load("alice", None)
    await service.sessions.delete("bob", sid)
    await service.sessions.load("alice", sid)
    await service.sessions.delete("alice", sid)
    with pytest.raises(DomainError):
        await service.sessions.load("alice", sid)
