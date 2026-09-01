"""พฤติกรรมแชตเมื่อใช้เอกสาร Q&A ที่อนุมัติแล้วเป็นแหล่งความรู้"""

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

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


class _FakeGeminiClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.models = SimpleNamespace(generate_content=self._generate_content)

    def _generate_content(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(text=next(self._responses))


@pytest.mark.asyncio
async def test_chat_answers_from_an_approved_qa_document() -> None:
    from tempfile import TemporaryDirectory

    question = "ถาม: ผู้เช่าบ้านขอใช้ไฟฟ้าใหม่ได้หรือไม่"
    answer = "ตอบ: ผู้เช่าบ้านยื่นคำขอได้เมื่อมีหลักฐานสิทธิครอบครองที่เกี่ยวข้อง"
    source_id = "qa/ผู้เช่าบ้านขอใช้ไฟฟ้าใหม่.docx"

    with TemporaryDirectory() as directory:
        source_root = Path(directory)
        _write_qa_docx(source_root / source_id, question, answer)
        client = _FakeGeminiClient(
            [
                f'{{"sourceIds":["{source_id}"]}}',
                f'{{"answer":"{answer}","citations":[{{"sourceId":"{source_id}","snippet":"{answer}"}}]}}',
            ]
        )
        backend = FullDocumentKnowledgeBackend(
            api_key="test-key",
            source_root=source_root,
            client_factory=lambda _: client,
        )
        agent = MainAgent(
            LLMClient(DemoLLMAdapter()),
            ToolRegistry(
                [
                    KnowledgeTool(backend),
                    OmsTool(
                        transport=httpx.MockTransport(
                            lambda request: httpx.Response(
                                200,
                                json={
                                    "caNumber": "100000000003",
                                    "customerFound": True,
                                    "network": {
                                        "meterId": "M",
                                        "transformerId": "T",
                                        "feederId": "F",
                                    },
                                    "activeEvent": None,
                                    "recommendedAction": "CREATE_METER_EVENT",
                                },
                            )
                        )
                    ),
                ]
            ),
        )

        response = await agent.handle_chat(
            ChatRequest(message="ผู้เช่าบ้านสามารถขอใช้ไฟฟ้าใหม่ได้ไหม")
        )

    assert response.message == answer
    assert response.citations[0].source_id == source_id
