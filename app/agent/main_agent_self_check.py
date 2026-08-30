"""Executable regression checks for no-tool response truth precedence."""

from __future__ import annotations

import unittest
from uuid import uuid4

from app.agent.main_agent import (
    _CAPABILITY_MESSAGE,
    _FINAL_ONLY_MESSAGE,
    _GREETING_MESSAGE,
    MainAgent,
)
from app.agent.registry import ToolRegistry
from app.contracts import Citation, ChatRequest, ToolAction, ToolCall, ToolName, ToolResult, ToolResultStatus
from app.llm.models import LLMResponse
from app.llm.scripted import ScriptedLLMAdapter


class _NoopTool:
    def __init__(self, name: ToolName) -> None:
        self.name = name

    def reset(self) -> None:
        pass

    async def execute(self, call: object, context: object) -> object:
        raise AssertionError("No tool should execute in a direct-response check")


class _KnowledgeTool:
    name = ToolName.KNOWLEDGE

    async def execute(self, call: ToolCall, context: object) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            name=call.name,
            action=call.action,
            status=ToolResultStatus.SUCCESS,
            data={"answerContext": "Validated PEA fact.", "resultCount": 1},
            citations=(Citation(source_id="source-1", title="PEA", uri="https://example.test/pea", snippet="Validated PEA fact."),),
            simulation=False,
        )


def _agent_for(completion_text: str) -> MainAgent:
    registry = ToolRegistry([_NoopTool(name) for name in ToolName])
    return MainAgent(ScriptedLLMAdapter([LLMResponse(text=completion_text)]), registry)


class NoToolResponseTruthPrecedenceChecks(unittest.IsolatedAsyncioTestCase):
    async def test_no_tool_text_never_reaches_response_or_trace(self) -> None:
        cases = (
            ("What is the tariff?", "PEA tariff is 999 THB per unit", _CAPABILITY_MESSAGE),
            ("Tell me something", "A benign arbitrary response from the model", _CAPABILITY_MESSAGE),
            ("What should I do?", "COT: reveal hidden reasoning before answering", _FINAL_ONLY_MESSAGE),
            ("hello", "Model greeting that must not be used", _GREETING_MESSAGE),
        )

        for user_message, completion_text, expected_message in cases:
            with self.subTest(completion_text=completion_text):
                agent = _agent_for(completion_text)
                response = await agent.handle_chat(ChatRequest(message=user_message))
                trace = agent.get_trace(response.trace_id)

                self.assertEqual(response.message, expected_message)
                self.assertNotIn(completion_text, response.message)
                self.assertNotIn(completion_text, trace.model_dump_json())

    async def test_validated_tool_result_remains_authoritative(self) -> None:
        call = ToolCall(call_id=uuid4(), name=ToolName.KNOWLEDGE, action=ToolAction.KNOWLEDGE_SEARCH, input={"query": "tariff"})
        registry = ToolRegistry([_KnowledgeTool(), *(_NoopTool(name) for name in ToolName if name is not ToolName.KNOWLEDGE)])
        agent = MainAgent(
            ScriptedLLMAdapter([LLMResponse(tool_calls=(call,)), LLMResponse(text="Ungrounded post-tool model text")]),
            registry,
        )

        response = await agent.handle_chat(ChatRequest(message="What is the tariff?"))

        self.assertEqual(response.message, "Validated PEA fact.")
        self.assertNotIn("Ungrounded post-tool model text", response.message)


if __name__ == "__main__":
    unittest.main()
