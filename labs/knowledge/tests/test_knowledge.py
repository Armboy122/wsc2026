import json

import pytest
from voice_assistant.contracts import SearchInput
from voice_assistant.plugins.knowledge import KnowledgePlugin
from conftest import publication


def test_retrieves_full_document_and_followup(settings):
    plugin = KnowledgePlugin(settings.knowledge_root, max_docs=1)
    result = plugin.search(SearchInput(query="ขอใช้ไฟฟ้าใหม่ต้องเตรียมอะไร"))
    assert result.evidence[0].source_id == "ขอใช้ไฟฟ้าใหม่.md"
    assert result.evidence[0].text == (settings.knowledge_root/"ขอใช้ไฟฟ้าใหม่.md").read_text()
    follow = plugin.search(SearchInput(query="แล้วต้องใช้อะไรอีก", previous_sources=("ขอใช้ไฟฟ้าใหม่.md",)))
    assert follow.evidence[0].source_id == "ขอใช้ไฟฟ้าใหม่.md"
    switched = plugin.search(SearchInput(query="คืนเงินประกันทำอย่างไร", previous_sources=("ขอใช้ไฟฟ้าใหม่.md",)))
    assert switched.evidence[0].source_id == "คืนเงินประกัน.md"


def test_tampered_document_fails_closed(settings):
    (settings.knowledge_root/"ขอใช้ไฟฟ้าใหม่.md").write_text("เปลี่ยนเนื้อหา")
    with pytest.raises(ValueError):
        KnowledgePlugin(settings.knowledge_root).search(SearchInput(query="ขอใช้ไฟฟ้า"))


def test_draft_future_expired_excluded(settings):
    manifest = settings.knowledge_root/"publication.json"
    original = json.loads(manifest.read_text())
    for change in [{"status": "draft"}, {"effective_from": "2999-01-01"}, {"effective_until": "2000-01-01"}]:
        data = json.loads(json.dumps(original))
        for doc in data["documents"]:
            doc.update(change)
        manifest.write_text(json.dumps(data))
        assert not KnowledgePlugin(settings.knowledge_root).search(SearchInput(query="ไฟฟ้า")).evidence


def test_budget_does_not_silently_truncate(settings):
    result = KnowledgePlugin(settings.knowledge_root, max_chars=10).search(SearchInput(query="ไฟฟ้า"))
    assert not result.evidence
    assert result.omitted > 0


def test_no_match_returns_empty(settings):
    assert not KnowledgePlugin(settings.knowledge_root).search(SearchInput(query="zxqv unicorn")).evidence


def test_oversized_first_document_does_not_hide_smaller_match(tmp_path):
    publication(tmp_path, {
        "ไฟฟ้า.md": "ไฟฟ้า " * 1000,
        "คู่มือ.md": "ขั้นตอนขอใช้ไฟฟ้าและหลักฐานประกอบ",
    })
    result = KnowledgePlugin(tmp_path, max_docs=1, max_chars=100).search(
        SearchInput(query="แล้วไฟฟ้า", previous_sources=("ไฟฟ้า.md",)))
    assert [d.source_id for d in result.evidence] == ["คู่มือ.md"]
    assert result.omitted == 1


def test_publication_path_escape_rejected(settings):
    path = settings.knowledge_root/"publication.json"
    data = json.loads(path.read_text())
    data["documents"][0]["path"] = "../outside.md"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        KnowledgePlugin(settings.knowledge_root).snapshot()
