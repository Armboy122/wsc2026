# Story 1 contract — ADK-only voice core

## Wire protocol (/ws/live) — unchanged, must keep working

Server → browser JSON events, exactly as the existing frontend expects:

| Event | Shape |
| --- | --- |
| ready | `{"type":"session.ready"}` |
| interruption | `{"type":"audio.interrupted"}` |
| transcript | `{"type":"transcript.user"\|"transcript.assistant","role":...,"text":...,"final":bool,"replace":bool}` |
| thinking | `{"type":"state","state":"thinking"}` |
| turn end | `{"type":"turn.complete"}` |
| error | `{"type":"error","message":<user-safe Thai>}` |

Server → browser binary frames carry PCM audio. Browser → server binary frames carry PCM16;
browser JSON must never invoke a tool.

Removed from this protocol in this story: the `agent.response` event's `confirm`/`reject`
operations, because the confirm/reject tools leave scope. A Knowledge tool result does not need
a dedicated browser event for Gemini to answer.

## Agent construction

```python
create_adk_agent(*, model: str, client: Client, knowledge_tool: BaseTool) -> Agent
```

No `MainAgent` parameter, no `WscTools`. `app/agent/adk_agent.py` and `app/runtime/adk_live.py`
must not import `app.agent.main_agent`.

## Session construction

```python
AdkLiveSession(*, api_key: str, model: str, voice: str,
               knowledge_tool: KnowledgeTool,
               session_service: BaseSessionService | None = None)
```

The Knowledge tool is required; ADK never constructs a business tool registry. `agent: MainAgent`
and `has_display` are removed — `has_display` existed only to drive VoiceBridge presentation for
OMS/VOC operational flows.

`/ws/live` always constructs `AdkLiveSession`; no runtime selector or channel parameter changes
the Voice runtime.

## RunConfig — preserved verbatim

`StreamingMode.BIDI`, audio response modality, prebuilt voice config,
input+output audio transcription, `START_OF_ACTIVITY_INTERRUPTS`,
`TURN_INCLUDES_ONLY_ACTIVITY`, `SessionResumptionConfig()`.

## Input validation — preserved verbatim

A PCM16 frame must be non-empty, even-length, and ≤ 32000 bytes, else `ValueError`.

## Safety invariants

- No raw ADK event, provider payload, or resumption handle reaches the browser.
- `google_adk` logger stays at WARNING.
- On teardown: close queue, cancel tasks, delete ADK session, close genai client, close socket.
- `/ws/live` still refuses to start when `GEMINI_API_KEY` is missing, with a user-safe Thai
  message and close code 1011.

## Testing decisions

Tests use a fake in-process tool and a fake WebSocket; no real Gemini call. Existing
`tests/test_adk_runtime.py` is the reference for the fake-socket pattern and is updated in
place. The former runtime-selector tests are category B (the selector feature is intentionally
removed) and are replaced by a test asserting `/ws/live` always serves ADK even when an obsolete
selector environment variable is present.
