# Ticket 001 — Build a deterministic approved-document catalog and loader

Type: implementation
Status: open
Blocked by: None

## TASK

Add deterministic catalog construction and safe full-Markdown loading for approved local Knowledge documents.

## FILES / COMPONENTS IN SCOPE

New or refactored `app/knowledge/catalog.py` and `app/knowledge/service.py` (or the smallest matching existing Knowledge modules), `knowledge/aliases/` parsing only as required, and focused Knowledge tests.

## MUST DO

- Catalog only approved local Markdown files under configured source root; retain relative POSIX source IDs and fail-closed symlink/path checks.
- Derive title/headings/topics and approved alias metadata deterministically without models, embeddings, or generated summaries.
- Implement selected-ID validation, maximum-document-count validation, full-file loading, logical source metadata, and total context-budget failure without truncation.
- Return a structured result containing complete documents and sources; unknown/unsafe IDs and over-budget requests return structured safe failures.
- Cover multiple selected documents and traversal/absolute/unknown IDs with regression tests.

## MUST NOT DO

- Do not call any generative model or choose documents based on a query in the server.
- Do not connect the catalog to ADK yet; Ticket 002 owns the model-facing selection contract.
- Do not modify approved Knowledge source documents.

## DEPENDENCIES

None.

## ACCEPTANCE CRITERIA

- Catalog metadata is deterministic and consists only of approved local Markdown.
- Full selected Markdown is returned unchanged; no silent truncation.
- Unsafe/unknown paths fail closed and budget overflow is explicit.
- Focused Knowledge tests pass.

## STOP CONDITION

Stop when the deterministic catalog/service boundary is tested; leave ADK wiring and deletion of legacy provider code to Ticket 002.
