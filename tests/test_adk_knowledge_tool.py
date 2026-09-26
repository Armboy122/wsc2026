"""The single ADK Knowledge capability: one query in, approved Q&A + chunks out."""

from __future__ import annotations

import ast
import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, cast

import pytest
from google.adk.tools.tool_context import ToolContext
from google.genai import Client

from app.agent.adk_agent import KNOWLEDGE_TOOL_NAME, AdkKnowledgeTool, create_adk_agent
from app.knowledge.index import (
    FakeEmbedder,
    IndexManager,
    SearchResult,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "knowledge" / "source"
ALIAS_ROOT = ROOT / "knowledge" / "aliases"
QA_SOURCE_ID = "qa/qa_ขั้นตอนขอคืนเงินประกันการใช้ไฟฟ้า.md"


@pytest.fixture(scope="module")
def real_manager(tmp_path_factory: pytest.TempPathFactory) -> IndexManager:
    """A real index over the approved corpus with the deterministic offline embedder."""
    manager = IndexManager(
        source_root=SOURCE_ROOT,
        alias_root=ALIAS_ROOT,
        index_dir=tmp_path_factory.mktemp("knowledge-index"),
        embedder=FakeEmbedder(),
        watch=False,
    )
    assert manager.rebuild() is True
    return manager


async def _run(tool: AdkKnowledgeTool, args: Any) -> dict[str, Any]:
    return await tool.run_async(args=args, tool_context=cast(ToolContext, object()))


def test_tool_declares_one_search_query_capability(real_manager: IndexManager) -> None:
    tool = AdkKnowledgeTool(real_manager)
    declaration = tool._get_declaration()

    assert tool.name == KNOWLEDGE_TOOL_NAME == "search_knowledge"
    assert declaration.name == "search_knowledge"
    schema = declaration.parameters_json_schema
    assert isinstance(schema, dict)
    assert schema["type"] == "object"
    assert schema["required"] == ["query"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"query"}
    query = schema["properties"]["query"]
    assert query["type"] == "string"
    assert query["minLength"] == 1
    assert query["maxLength"] == 500


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"query": ""},
        {"query": "   "},
        {"query": "ก" * 501},
        {"query": "ขอใช้ไฟฟ้า", "source_ids": ["alpha.md"]},
        {"query": "ขอใช้ไฟฟ้า", "extra": True},
        {"query": 123},
        {"query": None},
        {"query": ["ขอใช้ไฟฟ้า"]},
        {"source_ids": ["alpha.md"]},
    ],
)
@pytest.mark.asyncio
async def test_invalid_arguments_fail_closed(
    real_manager: IndexManager, args: dict[str, Any]
) -> None:
    result = await _run(AdkKnowledgeTool(real_manager), args)

    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_input"
    assert set(result) == {"status", "error"}


@pytest.mark.asyncio
async def test_maximum_length_query_is_accepted(real_manager: IndexManager) -> None:
    result = await _run(AdkKnowledgeTool(real_manager), {"query": "ก" * 500})

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_real_corpus_paraphrase_returns_approved_qa_first_with_sources(
    real_manager: IndexManager,
) -> None:
    result = await _run(
        AdkKnowledgeTool(real_manager),
        {"query": "ขอคืนเงินประกันมิเตอร์ไฟฟ้าทำอย่างไร"},
    )

    assert result["status"] == "success"
    assert set(result) == {"status", "approvedQa", "chunks", "sources"}
    assert result["approvedQa"], "expected the approved Q&A lane to answer first"
    first = result["approvedQa"][0]
    assert set(first) == {"sourceId", "title", "uri", "content"}
    assert first["sourceId"] == QA_SOURCE_ID
    assert first["uri"] == f"knowledge://source/{QA_SOURCE_ID}"
    assert first["content"].strip()
    for chunk in result["chunks"]:
        assert set(chunk) == {"sourceId", "title", "uri", "heading", "content"}
        assert isinstance(chunk["heading"], str)
        assert chunk["content"].strip()
    assert result["sources"], "every answer must carry provenance"
    assert result["sources"][0]["sourceId"] == QA_SOURCE_ID
    returned_ids = {hit["sourceId"] for hit in (*result["approvedQa"], *result["chunks"])}
    for source in result["sources"]:
        assert set(source) == {"sourceId", "title", "uri"}
        assert source["sourceId"] in returned_ids


@pytest.mark.asyncio
async def test_query_text_and_content_are_never_logged(
    real_manager: IndexManager, caplog: pytest.LogCaptureFixture
) -> None:
    query = "ขอคืนเงินประกันมิเตอร์ไฟฟ้าทำอย่างไร"
    with caplog.at_level(logging.INFO, logger="app.agent.adk_agent"):
        await _run(AdkKnowledgeTool(real_manager), {"query": query})

    assert "knowledge_search status=success" in caplog.text
    assert query not in caplog.text
    assert "คำตอบที่" not in caplog.text


@pytest.mark.asyncio
async def test_index_not_ready_returns_unavailable(tmp_path: Path) -> None:
    manager = IndexManager(
        source_root=SOURCE_ROOT,
        alias_root=ALIAS_ROOT,
        index_dir=tmp_path / "never-built",
        embedder=FakeEmbedder(),
        watch=False,
    )

    result = await _run(AdkKnowledgeTool(manager), {"query": "ค่าไฟฟ้า"})

    assert result["status"] == "error"
    assert result["error"]["code"] == "unavailable"
    assert set(result) == {"status", "error"}


class _ExplodingManager:
    def search(self, query: str) -> SearchResult:  # pragma: no cover - always raises
        raise RuntimeError("SECRET provider detail")


@pytest.mark.asyncio
async def test_unexpected_failure_returns_internal_without_leaking_details() -> None:
    tool = AdkKnowledgeTool(cast(IndexManager, _ExplodingManager()))

    result = await _run(tool, {"query": "ค่าไฟฟ้า"})

    assert result["status"] == "error"
    assert result["error"]["code"] == "internal"
    assert "SECRET" not in str(result)


class _SlowManager:
    """Blocks its calling thread until the test releases it, mimicking a slow search."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def search(self, query: str) -> SearchResult:
        self.started.set()
        if not self.release.wait(timeout=5):  # pragma: no cover - only on a broken offload
            raise TimeoutError("search was never released")
        return SearchResult(query=query, qa=(), chunks=(), sources=(), total_chars=0)


@pytest.mark.asyncio
async def test_search_is_offloaded_so_the_event_loop_keeps_running() -> None:
    slow = _SlowManager()
    tool = AdkKnowledgeTool(cast(IndexManager, slow))

    async with asyncio.timeout(5):
        task = asyncio.create_task(_run(tool, {"query": "ค่าไฟฟ้า"}))
        # The event loop reaches this point only if the blocking search is off-loaded.
        ticks = 0
        while not slow.started.is_set() and ticks < 500:
            ticks += 1
            await asyncio.sleep(0.005)
        assert slow.started.is_set()
        assert not task.done()
        slow.release.set()
        result = await task

    assert result["status"] == "success"


def test_agent_instruction_carries_the_qa_rule_without_a_catalog(
    real_manager: IndexManager,
) -> None:
    client = Client(api_key="test")
    try:
        tool = AdkKnowledgeTool(real_manager)
        agent = create_adk_agent(model="fake-live", client=client, knowledge_tool=tool)
    finally:
        client.close()

    assert agent.tools == [tool]
    instruction = agent.instruction
    assert isinstance(instruction, str)
    assert "search_knowledge" in instruction
    assert "คำตอบที่อนุมัติ" in instruction
    assert "1129" in instruction
    assert "get_knowledge" + "_documents" not in instruction
    assert "catalog" not in instruction.lower()
    assert '"sourceId"' not in instruction
    # No catalog JSON and no ADK ``{...}`` template variables may remain.
    assert "{" not in instruction
    assert "}" not in instruction


def test_agent_exposes_exactly_one_knowledge_tool(real_manager: IndexManager) -> None:
    client = Client(api_key="test")
    try:
        agent = create_adk_agent(
            model="fake-live",
            client=client,
            knowledge_tool=AdkKnowledgeTool(real_manager),
        )
    finally:
        client.close()

    names = [getattr(tool, "name", None) for tool in agent.tools]
    assert names == ["search_knowledge"]


def test_knowledge_modules_never_import_a_generative_provider() -> None:
    modules = sorted(ROOT.joinpath("app", "knowledge").rglob("*.py"))
    assert modules, "expected deterministic Knowledge modules"

    forbidden_roots = ("google", "adk", "genai", "openai", "anthropic")
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_roots, module
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden_roots, module
            elif isinstance(node, ast.Attribute):
                assert node.attr != "generate_content", module
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"generate_content", "generate_content_async"}, module
