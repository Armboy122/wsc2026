# PEA One Agent — Competition Demo UI (AI-05)

Lightweight static one-screen chat UI for the hackathon demo. No framework, no build step,
no install step — four plain files: `index.html`, `styles.css`, `app.js`, and this README.

## What it is

A single-screen conversation interface (Thai-first) that talks **only** to the frozen v1
HTTP contract defined in `../CONTRACTS.md` / `../app/contracts.py`:

| Route | Used for |
|---|---|
| `POST /api/v1/chat` | Send a message, render the assistant reply, citations, tool chips, and pending action |
| `POST /api/v1/actions/{pendingActionId}/confirm` | Human confirmation of a prepared write (optional `confirmationNote`) |
| `POST /api/v1/actions/{pendingActionId}/reject` | Terminal rejection (required non-empty `reason`) |
| `GET /api/v1/traces/{traceId}` | Ordered, redacted trace events in the "การตรวจสอบ" drawer |
| `POST /api/v1/reset` | Clear conversations, pending actions, simulated state, and traces |

No other endpoints are called (`/health` is not needed by this UI). Field names follow the
camelCase JSON convention of the frozen models exactly (`conversationId`, `traceId`,
`pendingAction`, `preparedInput`, `idempotencyKey`, …).

## Running it

The UI calls the API with same-origin relative paths (`/api/v1/...`), so the expected
deployment is the single FastAPI demo process serving this directory at `/` (e.g. a
StaticFiles mount) — the same origin then serves both the page and the API.

- **Integrated demo:** serve `web/` from the FastAPI process and open the app URL.
- **Visual preview only** (no backend): `python3 -m http.server 8080 --directory web`
  and open `http://localhost:8080`. The page renders fully; every API call will surface
  through the designed error state ("ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้"), which is itself
  part of the demo script.
- Opening `index.html` directly from the filesystem also works for visual inspection;
  fonts fall back gracefully if offline (Anuphan → Thai system fallbacks).

## Features

- **Conversation**: user/assistant bubbles with timestamps, auto-scroll, typing indicator.
- **Input & send**: auto-growing textarea (max 4,000 chars per contract), Enter to send,
  Shift+Enter for newline, five scripted prompt buttons (knowledge · Sabuy read · Sabuy
  write · VOC case · OMS outage report — one journey per tool family).
- **Loading / error states**: busy lock during a round-trip, normalized error notices for
  404/409/422/5xx and network failure; FastAPI `detail` payloads are decoded into a
  user-safe message.
- **Citations**: rendered only from `ChatResponse.citations` (Gemini File Search), with
  title, snippet, page chip, and source link. Simulated facts are never shown as citations.
- **Trace**: drawer for the latest `traceId` with ordered events (Thai label + contract
  kind), refresh, and expandable redacted `data` JSON.
- **Pending-action preview**: card with status badge, tool + action, simulated label,
  redacted `preparedInput`, and note/reason field.
- **Confirm / cancel**: confirm posts `confirmationNote` (optional); reject requires a
  non-empty reason (validated client-side before the call). Terminal cards show the
  receipt (receiptId / caseId / reportId) or the rejection; buttons lock while a decision
  is in flight and 409s surface inline on the card.
- **Reset**: clears server demo state and the local screen; conversation restarts fresh.
- **SIMULATED BACKEND badge**: always visible in the header, plus per-result SIMULATED
  chips and a simulated-only footnote on every submitted action.

## Safety posture

- **No chain-of-thought is ever displayed.** Trace rendering shows only the contract event
  kinds; any thought-like keys (`thought`, `reasoning`, `chain-of-thought`, …) are
  defensively redacted client-side even if a backend bug leaked them.
- **Never implies production data.** Every operational surface repeats the simulated
  label; only knowledge citations are presented as real retrieved sources.
- **Writes leave the browser only through the confirm/reject routes.** Nothing in the chat
  path can submit a write, and no client-side flag is ever trusted as a confirmation.

## Accessibility & design

- Mobile-first single column (`100dvh` shell, sticky composer, horizontally scrolling
  prompt chips); on desktop the conversation centers at a comfortable reading width.
- Purple professional system: ink-violet header with an engineering grid texture, violet
  actions, amber reserved for simulation labelling, green/red only for outcomes.
- Fonts: Anuphan (Thai/Latin UI) + IBM Plex Mono (ids, trace, timestamps) via Google
  Fonts, with system Thai fallbacks when offline.
- WCAG-minded: skip link, landmarks, `role="log"` conversation, `aria-live` status
  announcements, focus management on pending actions, ≥44px touch targets, visible
  focus rings, `prefers-reduced-motion` support, and contrast-checked palette.

## Ownership

This directory (`web/**`) is owned by AI-05. `ARCHITECTURE.md`, `CONTRACTS.md`, and
`app/contracts.py` are read-only references for this UI and are never modified here.
