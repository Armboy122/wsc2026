# Ticket 002 — Let Gemini Live select and retrieve source documents

Type: implementation
Status: open
Blocked by: 001

## TASK

Expose the deterministic catalog to the ADK Voice Agent, implement the selected-source Knowledge tool result, and remove all generative calls from Knowledge.

## FILES / COMPONENTS IN SCOPE

`app/agent/adk_agent.py`, ADK Knowledge tool/runtime wiring, deterministic Knowledge modules, obsolete Knowledge provider/router/answer implementation and tests, configuration only where required for this seam.

## MUST DO

- Give ADK a compact catalog of source IDs, titles, topics/headings, and approved aliases.
- Expose one focused `get_knowledge_documents(source_ids)` capability; server validates IDs and returns the structured complete documents/source provenance from Ticket 001.
- Ensure the tool does not generate an answer; the same Gemini Live session receives the document result and answers.
- Remove Knowledge model clients, router/answer calls, and their settings from the active Knowledge implementation.
- Add tests proving source selection results return into the same ADK session and Knowledge makes zero generative provider calls.

## MUST NOT DO

- Do not introduce another model, MCP, embeddings, vector search, chunking, cloud Knowledge store, or auto-loading of all documents.
- Do not expose absolute paths or read arbitrary model-supplied paths.
- Do not change realtime transport behavior from Story 1.

## DEPENDENCIES

Ticket 001.

## ACCEPTANCE CRITERIA

- Gemini Live receives the catalog and chooses source IDs.
- One Knowledge tool returns complete validated documents and provenance into the same Live session.
- Static/runtime tests establish zero Knowledge generative API calls.
- Focused and full test suites pass.

## STOP CONDITION

Stop once Gemini Live → deterministic local documents → same Gemini Live is tested. Do not begin platform deletion.
