"""The single ADK Knowledge capability: selected source IDs in, complete documents out."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

import pytest
from google.adk.tools.tool_context import ToolContext
from google.genai import Client

from app.agent.adk_agent import KNOWLEDGE_TOOL_NAME, AdkKnowledgeTool, create_adk_agent
from app.knowledge.catalog import KnowledgeCatalog
from app.knowledge.service import KnowledgeDocumentService

ALPHA = "# บริการอัลฟ่า\n\n## เอกสารที่ต้องใช้\n\nสำเนาบัตรประชาชน\n"
BETA = "# บริการบีต้า\n\nเนื้อหาบีต้า\n"


@pytest.fixture
def service(tmp_path: Path) -> KnowledgeDocumentService:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "alpha.md").write_text(ALPHA, encoding="utf-8")
    (source / "nested" / "beta.md").write_text(BETA, encoding="utf-8")
    (tmp_path / "outside.md").write_text("# ลับ\n", encoding="utf-8")
    return KnowledgeDocumentService(
        KnowledgeCatalog(source, alias_root=tmp_path / "aliases"), max_documents=2
    )


async def _run(tool: AdkKnowledgeTool, args: Any) -> dict[str, Any]:
    return await tool.run_async(args=args, tool_context=cast(ToolContext, object()))


def test_tool_declares_one_focused_source_id_capability(service: KnowledgeDocumentService) -> None:
    tool = AdkKnowledgeTool(service)
    declaration = tool._get_declaration()

    assert tool.name == KNOWLEDGE_TOOL_NAME == "get_knowledge_documents"
    assert declaration.name == "get_knowledge_documents"
    schema = declaration.parameters_json_schema
    assert isinstance(schema, dict)
    assert schema["required"] == ["source_ids"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"source_ids"}
    assert schema["properties"]["source_ids"]["maxItems"] == 2


@pytest.mark.asyncio
async def test_tool_returns_complete_documents_and_provenance(
    service: KnowledgeDocumentService,
) -> None:
    result = await _run(AdkKnowledgeTool(service), {"source_ids": ["nested/beta.md", "alpha.md"]})

    assert result["status"] == "success"
    assert [document["sourceId"] for document in result["documents"]] == ["nested/beta.md", "alpha.md"]
    assert result["documents"][1] == {
        "sourceId": "alpha.md",
        "title": "บริการอัลฟ่า",
        "uri": "knowledge://source/alpha.md",
        "content": ALPHA,
    }
    assert result["documents"][0]["content"] == BETA
    assert result["sources"] == [
        {"sourceId": "nested/beta.md", "title": "บริการบีต้า", "uri": "knowledge://source/nested/beta.md"},
        {"sourceId": "alpha.md", "title": "บริการอัลฟ่า", "uri": "knowledge://source/alpha.md"},
    ]
    # The tool never answers: no answer/summary field exists in the result.
    assert set(result) == {"status", "documents", "sources"}
    # Only logical provenance is exposed; the server's absolute source root never is.
    assert str(service.catalog.source_root.resolve()) not in str(result)
    assert str(service.catalog.source_root) not in str(result)


@pytest.mark.parametrize(
    "args",
    [
        {"source_ids": ["../outside.md"]},
        {"source_ids": ["/etc/passwd"]},
        {"source_ids": ["missing.md"]},
        {"source_ids": ["alpha.md", "alpha.md"]},
        {"source_ids": ["alpha.md", "nested/beta.md", "alpha.md"]},
        {"source_ids": []},
        {"source_ids": "alpha.md"},
        {"source_ids": ["alpha.md"], "path": "/etc/passwd"},
        {"query": "ขอใช้ไฟฟ้า"},
        {},
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_unsafe_selection_fails_closed(
    service: KnowledgeDocumentService, args: dict[str, Any]
) -> None:
    result = await _run(AdkKnowledgeTool(service), args)

    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_input"
    assert "documents" not in result
    assert "ลับ" not in str(result)


@pytest.mark.asyncio
async def test_over_budget_selection_is_structured_failure_without_truncation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "big.md").write_text("# ใหญ่\n\n" + "ก" * 500, encoding="utf-8")
    service = KnowledgeDocumentService(
        KnowledgeCatalog(source, alias_root=tmp_path / "aliases"), max_total_chars=100
    )

    result = await _run(AdkKnowledgeTool(service), {"source_ids": ["big.md"]})

    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_input"
    assert "documents" not in result


def test_adk_voice_prompt_is_short_and_knowledge_only() -> None:
    prompt = Path("app/prompts/adk_voice.md").read_text(encoding="utf-8").lower()

    assert "get_knowledge_documents" in prompt
    assert "catalog" in prompt
    assert "เอกสาร" in prompt
    for excluded in ("oms", "voc", "ca number", "pending", "confirm", "reject", "consent", "idempotency", "write", "outage", "complaint"):
        assert excluded not in prompt


def test_adk_agent_exposes_only_knowledge_and_voice_runtime_has_no_main_agent_import(
    service: KnowledgeDocumentService,
) -> None:
    knowledge_tool = AdkKnowledgeTool(service)
    client = Client(api_key="test")
    try:
        agent = create_adk_agent(
            model="gemini-live-test", client=client, knowledge_tool=knowledge_tool
        )
        assert len(agent.tools) == 1
        assert agent.tools[0] is knowledge_tool
        assert '"sourceId":"nested/beta.md"' in str(agent.instruction)
    finally:
        client.close()

    for filename in ("app/agent/adk_agent.py", "app/runtime/adk_live.py"):
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert "app.agent.main_agent" not in imported_modules
        assert "app.tools.knowledge_tool" not in imported_modules
        assert "app.backends.full_document_knowledge" not in imported_modules


def test_active_knowledge_path_has_no_generative_provider_calls() -> None:
    """Static: the ADK Knowledge tool delegates only to deterministic Knowledge modules."""
    tree = ast.parse(Path("app/agent/adk_agent.py").read_text(encoding="utf-8"))
    tool_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AdkKnowledgeTool"
    )
    called = {
        node.func.attr
        for node in ast.walk(tool_class)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "generate_content" not in called
    assert "generate_content_async" not in called
    for path in Path("app/knowledge").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("google.genai", "from google import genai", "generate_content", "openai"):
            assert forbidden not in source, (path, forbidden)
