# Contract

- The public application surface is the static Voice UI, `GET /health`, and `WS /ws/live`, plus only infrastructure required to host these.
- Settings and dependency injection are limited to app environment/log level, Gemini Live credentials/model/voice, Knowledge source root, and proven-required transport settings.
- Remove active and dead MainAgent/planner, legacy voice/VoiceBridge, OMS/VOC, business adapters, Chat/LINE routes and runtimes, pending-action/confirmation machinery, registrations, config, tests, and dependencies when no remaining valid use exists.
- Keep ADK/Gemini Live and deterministic Knowledge. Do not touch approved source content.
- Rewrite README, ARCHITECTURE, PRD/CONTRACTS if retained, Knowledge README, and ADK migration notes to describe the actual Voice-only system. Remove stale docs that assert removed features exist.
- Preserve the existing functional Voice UI while removing obsolete Chat/business workflow UI and API references.

## Testing Decisions

Validate the FastAPI app starts, `/health` responds, `/ws/live` serves ADK without a runtime selector, the static UI is served, and the full pytest suite passes. Add architecture assertions for absent runtime imports/routes/settings and Knowledge's no-LLM boundary. Run JS syntax checks for changed frontend files. Do not claim real microphone/provider, Thai speech, barge-in latency, or performance results without actually measuring them; document those as manual acceptance requirements when credentials/device are absent.
