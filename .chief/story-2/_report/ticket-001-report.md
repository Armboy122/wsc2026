# Ticket 001 Report — Deterministic Knowledge catalog and loader

## Implementation Summary

Added a deterministic, offline Knowledge catalog and a selected-document service under
`app/knowledge/`. Catalog construction reads only approved local Markdown under the configured
source root, derives title and headings from the Markdown itself, and attaches
maintainer-approved alias metadata. It performs no network, model, embedding, or summary work.

`KnowledgeDocumentService.select(source_ids)` validates a model-selected ID list against the
catalog, then returns complete, unmodified document content with `sourceId`, title, and logical
`knowledge://source/<sourceId>` provenance. Unsafe or unknown selections, duplicates, count
limits, and total context-budget overflow return structured safe failures instead of raising,
truncating, or guessing.

ADK wiring is deliberately not connected here; Story 2 Ticket 002 owns the model-facing
selection contract.

## Files Changed

- `app/knowledge/__init__.py` (new)
- `app/knowledge/catalog.py` (new)
- `app/knowledge/service.py` (new)
- `tests/test_knowledge_catalog.py` (new)
- `tests/test_knowledge_documents.py` (new)

## Verification

- Full suite: `.venv/bin/python -m pytest -q` — **384 passed** (352 baseline + 32 new).
- New tests: `tests/test_knowledge_catalog.py` + `tests/test_knowledge_documents.py` — 32 passed.
- Real corpus: catalog discovers **45 approved documents** (47 `.md` files minus 2 `README.md`).
- LSP diagnostics on all new files — 0 findings.
- `git diff --check` — clean.
- Static test asserts `app/knowledge/*.py` imports no generative provider and calls no
  `generate_content`.

## Acceptance Status

**PASS** — reviewer: `xai/grok-4.7` (read-only acceptance review via pi, 2026-09-26).
Verdict: PASS, no blocking findings. The reviewer re-ran the focused Knowledge tests
(32 passed) and the full suite (384 passed), confirmed only the new Knowledge files are
changed, no edits to `knowledge/source/` or `knowledge/aliases/`, 45 catalogued documents
(only the two `README.md` files excluded), and that importing the Knowledge modules loads no
`google`/`genai`/`openai`/`anthropic` module.

Deviation: reviewer was `xai/grok-4.7` instead of Sol because the Codex usage limit was
reached; approved by owner 2026-09-26.

An earlier Sol attempt failed with `Codex error: The usage limit has been reached`.

## Notes and Residual Risks

- `app/main.py` Pyright findings observed during this work are pre-existing baseline issues: the
  file is byte-identical to `HEAD` (`git diff` empty) and was not touched by this ticket.
- Default limits are `max_documents=5` and `max_total_chars=120000`; they are constructor
  parameters, not yet wired to `Settings` (Ticket 002 owns that seam).
- Alias rules that reference unknown source IDs raise at catalog construction, matching the
  existing fail-closed startup behavior.
- No live model, embedding, or microphone behavior was exercised or claimed.
- Reviewer non-blocking notes (not fixed; outside the ticket's acceptance criteria):
  - `catalog.py` title scan does not track fenced-code state (the heading loop does); a fenced
    `#` line before the real H1 could become the title. Not hit by the approved corpus.
  - Compact catalog entries keep only the first 12 headings (10 approved documents have more).
    This is catalog metadata only; full Markdown content is never truncated.
  - `service.py` reads the path captured at catalog build without re-checking symlink/root
    containment at read time; a local symlink swap after startup could be followed.
    Model-selected IDs still cannot escape the allowlist.
  - An unreadable or non-UTF-8 approved file is skipped at catalog build without a startup
    signal; selection of it stays fail-closed.
