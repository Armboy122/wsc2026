# PEA One Agent — Demo Architecture

## Decision summary

Build one FastAPI process with exactly one **Main Agent** and four callable top-level tool modules:

1. `knowledge_tool`
2. `sabuy_tool`
3. `voc_tool`
4. `oms_tool`

This is deliberately a small, deep module design: HTTP handlers only validate and translate requests; the Main Agent owns orchestration, policy, and user-facing answers. Tool modules own their respective data semantics and simulated-backend details. No LangGraph, LangChain, queues, microservices, custom vector database, or real PEA integration is in scope.

## Demo topology

```text
Browser / judge client
        |
        v
FastAPI routes (/api/v1/*, /health)
        |
        +-- Request/response contract validation (Pydantic)
        |
        v
Main Agent  <---->  LLMAdapter (judge-provided LLM implementation)
    |  |  |  |
    |  |  |  +--> oms_tool ------> SimulatedOmsBackend
    |  |  +-----> voc_tool ------> SimulatedVocBackend
    |  +--------> sabuy_tool ----> SimulatedSabuyBackend
    +-----------> knowledge_tool -> Gemini File Search Hosted RAG
        |
        v
TraceStore + PendingActionStore (in-process, resettable demo state)
```

## Runtime modules and seams

### HTTP module

**Interface:** routes documented in `CONTRACTS.md`. It validates inputs, invokes one Main Agent operation, and returns frozen contract models. It contains no business policy and never invokes a tool directly.

### Main Agent module

**Interface:** `handle_chat`, `confirm_pending_action`, `reject_pending_action`, `get_trace`, and `reset_demo`.

It is the only model-driven orchestrator. It:

- receives the user message and conversation state;
- calls only the four registered top-level tools;
- treats tool results as authoritative facts over model text;
- creates a pending action after a successful `prepare_*` result;
- submits a write only after the explicit confirm route is called;
- emits ordered trace events;
- produces the final chat response.

It must not expose sub-agents, agents per tool, or undeclared tools. A tool may have internal helper code, but no additional top-level tool is registered with the LLM.

### `LLMAdapter` seam

The Main Agent depends on a provider-agnostic interface, not a judge SDK:

```python
class LLMAdapter(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
```

`LLMRequest` contains messages, the fixed four-tool catalogue, and a correlation id. `LLMResponse` contains text plus zero or more `ToolCall` values. The judge-specific adapter translates its SDK structures into these local contracts. A `ScriptedLLMAdapter` is sufficient for deterministic demos/tests.

The adapter never contains PEA policy, secrets in trace output, or direct backend access.

### Tool module seam

Each tool has one narrow interface:

```python
class Tool(Protocol):
    name: ToolName
    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult: ...
```

The Tool Registry is fixed at startup to exactly the four required tool names. It rejects unknown names and action/name mismatches before a backend call.

### Backend adapters

- `GeminiFileSearchKnowledgeBackend` calls Gemini File Search Hosted RAG only. The tool forwards retrieval query and turns returned source metadata into citations. It does not embed, chunk, index, rank, or persist documents itself.
- `SimulatedSabuyBackend`, `SimulatedVocBackend`, and `SimulatedOmsBackend` use deterministic in-memory fixture data. Their responses include `simulation: true` and no claim is made that an action reached PEA.

For the 2-day demo, stores are process-local and resettable. State loss after restart is acceptable and documented in the UI/demo script.

## Write safety state machine

All mutating operations follow this invariant:

```text
prepare_* -> pending_confirmation -> confirm endpoint -> submit_* -> submitted | failed
                              \-> reject endpoint -> rejected
```

Rules:

1. A chat request may call read actions and `prepare_*` actions only.
2. `prepare_*` validates the requested payload and returns a `PendingAction`; it makes no simulated side effect.
3. Only `POST /api/v1/actions/{pending_action_id}/confirm` may transition a pending action to submission.
4. Confirmation must be idempotent: repeated confirmations return the original terminal result and must not submit twice.
5. Rejection is terminal and idempotent; a rejected action can never be submitted.
6. `submit_*` is an internal Main Agent-to-tool call, not an LLM-selected action during chat.
7. Trace records preparation, confirmation/rejection, submission, and result with redacted payloads.

No endpoint accepts a client instruction such as `confirmed=true` as a substitute for the confirm route.

## Data and truth precedence

1. Successful typed tool results are authoritative for operational facts and transaction outcome.
2. Gemini retrieval output is authoritative only for the cited knowledge it returns.
3. The LLM may explain facts but must not invent account, outage, case, payment, or citation details.
4. If a tool fails or has no result, the response states the limitation rather than fabricating a result.

## Error posture

- Invalid request or contract violation: HTTP 422.
- Missing conversation, trace, or pending action: HTTP 404.
- Invalid state transition (for example, confirming rejected): HTTP 409.
- Gemini/judge LLM/simulated backend unavailable: normalized typed failure, HTTP 502 only when the route cannot produce a valid chat/action response.
- Unknown tool, unknown action, or an action not permitted in the current flow: fail closed and add a trace error event.

## File ownership for parallel workers

| Owner | Exclusive files/directories | Contract dependency |
|---|---|---|
| Lead/integration | `ARCHITECTURE.md`, `CONTRACTS.md`, `app/contracts.py`, `app/main.py`, `tests/test_contracts.py` | Owns frozen contracts and route wiring; approves all contract changes. |
| Worker A — agent | `app/agent/`, `app/llm/` | Imports only `app.contracts`; calls only `ToolRegistry` interface. |
| Worker B — knowledge | `app/tools/knowledge_tool.py`, `app/backends/gemini_file_search.py` | May not add a vector DB or change public contracts. |
| Worker C — simulated operations | `app/tools/sabuy_tool.py`, `app/tools/voc_tool.py`, `app/tools/oms_tool.py`, `app/backends/simulated_*.py` | Uses actions and models frozen in `app.contracts`. |
| Worker D — verification/docs | `tests/`, `README.md`, `demo/` | Does not modify production modules or contracts. |

Shared files are read-only to workers unless the lead explicitly assigns a change. Workers add new files only in their owned directory. Any change to `app/contracts.py` or either root Markdown contract document is a lead-reviewed integration change.

## 2-day sequence

**Day 1:** lock contracts; create route and model validation stubs; implement deterministic simulated backends; implement Gemini hosted retrieval adapter; implement scripted/judge adapter seam; prove prepare/confirm/reject trace.

**Day 2:** connect the judge adapter; curate Gemini File Search corpus; add fixtures and failure paths; rehearse four scripted demo journeys; run the integration checklist.

## Integration checklist

- [ ] Startup registers exactly `knowledge_tool`, `sabuy_tool`, `voc_tool`, and `oms_tool` once each.
- [ ] `POST /api/v1/chat` validates the frozen request/response models and returns a trace id.
- [ ] Knowledge search returns Gemini File Search citations; no local embedding/index/vector dependency exists.
- [ ] Sabuy, VOC, and OMS responses visibly declare `simulation: true`.
- [ ] Each write journey proves prepare -> human confirm -> submit; direct submit from chat is rejected.
- [ ] Repeat confirm does not duplicate a simulated payment, VOC case, or outage report.
- [ ] Reject is terminal and leaves no simulated side effect.
- [ ] `GET /api/v1/traces/{trace_id}` shows ordered, redacted events for each journey.
- [ ] `POST /api/v1/reset` clears demo state, including pending actions and traces.
- [ ] `/health` reports process health and adapter readiness without exposing credentials.

## Definition of Done

The prototype is demo-ready when the public routes in `CONTRACTS.md` work against the frozen Pydantic models; the Main Agent can explain a cited Gemini hosted-RAG answer; it can read simulated Sabuy/VOC/OMS data; and it can prepare, visibly await a human confirmation, then submit exactly one simulated write with an auditable trace. It must run as one FastAPI process, retain exactly one Main Agent and the four declared top-level tools, and clearly label all non-knowledge operational data as simulated.
