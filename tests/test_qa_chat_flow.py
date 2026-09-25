"""พฤติกรรมแชตเมื่อใช้เอกสาร Q&A ที่อนุมัติแล้วเป็นแหล่งความรู้"""

from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
import pytest

from app.agent.main_agent import MainAgent
from app.agent.registry import ToolRegistry
from app.backends.full_document_knowledge import FullDocumentKnowledgeBackend
from app.contracts import ChatRequest
from app.llm import DemoLLMAdapter, LLMClient
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.oms_tool import OmsTool


def _write_qa_docx(path: Path, question: str, answer: str) -> None:
    path.parent.mkdir(parents=True)
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in (question, answer)
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def _write_qa_markdown(path: Path, question: str, answer: str) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(f"# {question}\n\n{answer}\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_chat_knowledge_fails_closed_after_knowledge_model_removal() -> None:
    """Story 2 Ticket 002 removed Knowledge router/answer model calls.

    Legacy Chat (removed in Story 3) must not fabricate an answer or citations; the Knowledge
    tool returns a structured unavailable error instead.
    """
    from tempfile import TemporaryDirectory

    question = "ถาม: ผู้เช่าบ้านขอใช้ไฟฟ้าใหม่ได้หรือไม่"
    answer = "ตอบ: ผู้เช่าบ้านยื่นคำขอได้เมื่อมีหลักฐานสิทธิครอบครองที่เกี่ยวข้อง"
    source_id = "qa/ผู้เช่าบ้านขอใช้ไฟฟ้าใหม่.docx"

    with TemporaryDirectory() as directory:
        source_root = Path(directory)
        _write_qa_docx(source_root / source_id, question, answer)
        backend = FullDocumentKnowledgeBackend(source_root=source_root)
        agent = MainAgent(
            LLMClient(DemoLLMAdapter()),
            ToolRegistry(
                [
                    KnowledgeTool(backend),
                    OmsTool(
                        base_url="http://oms.test/api/v1/oms",
                        transport=httpx.MockTransport(
                            lambda request: httpx.Response(500)
                        ),
                    ),
                ]
            ),
        )

        response = await agent.handle_chat(
            ChatRequest(message="ผู้เช่าบ้านสามารถขอใช้ไฟฟ้าใหม่ได้ไหม")
        )

    assert answer not in response.message
    assert response.citations == ()
    knowledge_results = [r for r in response.tool_results if r.name.value == "knowledge_tool"]
    assert knowledge_results
    assert all(r.status.value == "error" for r in knowledge_results)
    assert all(r.error is not None and r.error.code.value == "unavailable" for r in knowledge_results)


def test_catalog_reads_markdown_and_excludes_policy_readmes(tmp_path: Path) -> None:
    source_id = "qa/ผู้เช่าบ้านขอใช้ไฟฟ้าใหม่.md"
    question = "ถาม: ผู้เช่าบ้านขอใช้ไฟฟ้าใหม่ได้หรือไม่"
    answer = "ตอบ: ผู้เช่าบ้านยื่นคำขอได้เมื่อมีหลักฐานสิทธิครอบครองที่เกี่ยวข้อง"
    _write_qa_markdown(tmp_path / source_id, question, answer)
    (tmp_path / "README.md").write_text("# นโยบาย corpus\n", encoding="utf-8")
    (tmp_path / "qa" / "README.md").write_text("# นโยบาย Q&A\n", encoding="utf-8")

    backend = FullDocumentKnowledgeBackend(source_root=tmp_path)

    catalog = backend._catalog()

    assert list(catalog) == [source_id]
    assert catalog[source_id].title == question
    assert backend._full_text(catalog[source_id]) == f"# {question}\n\n{answer}\n"
