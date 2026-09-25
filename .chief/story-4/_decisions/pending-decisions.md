# Decisions (owner) — Story 4

Status: **DECIDED** by the owner on 2026-09-26. D0 is approved; D1–D7 use the recorded defaults.

| ID | Question | Decision (2026-09-26) | Affects |
| --- | --- | --- | --- |
| D0 | Story 4 contradicts `_rules/_goal/product-scope.md` (marked FINAL): catalog selection by Gemini (constraint 3), full documents returned (4), and project rule "no embeddings/RAG". Approve amending those rules? | **Approved.** The rules change from "Gemini selects whole documents from a catalog, no RAG" to local RAG as planned (hybrid search, Q&A first). Ticket 003 updates `product-scope.md`, `project.md` and `checks.md`. | all |
| D1 | Installment policy conflict: Q&A `qa_ค้างชำระค่าไฟ_แบ่งชำระ.md` says installment only at the office; PEA doc (`PEA_ลงทะเบียนขอผ่อนชำระค่าไฟฟ้า.md` / `PEA_eBill_ผ่อนชำระ_คืนเงินประกัน.md`) describes an online portal. | **Q&A wins at runtime** (precedence rule). No document is edited. The owner updates source files themselves if needed. | 003, eval gold |
| D2 | Add the PEA Work Manual as a Knowledge source? | **No** Work Manual in Story 4. Drop-in works later once an approved Markdown copy exists; re-run eval after adding. | content only |
| D3 | Acceptable voice latency for a knowledge turn. | **Hybrid `search_knowledge` is the primary path** (~160 ms measured on CPU, excluding Gemini). Deep fallback optional (see D5). Measure end-to-end with real Live later. | 003, 005 |
| D4 | Self-host bge-m3 (~2.3 GB model, CPU, adds `sentence-transformers`/torch)? | **Yes, self-host bge-m3.** `gemini-embedding` stays a config swap behind the `Embedder` protocol. | 001, 002 |
| D5 | Build `ask_knowledge_deep` (second, non-conversational Gemini Flash call with context caching)? It conflicts with "no second answering LLM". | **No deep fallback for now.** Ticket 005 stays blocked / not built. | 005 |
| D6 | Re-measure with the Gemini API key (Gemini as answer model, possibly gemini-embedding). | **Later**, via the ticket 004 harness with the Gemini adapter; the owner runs it with their key. | 004 |
| D7 | Eval corpus in `~/rag-eval` also included `docs/research/electricity-tariff-sep-2569.md`, which is not under `knowledge/source/`. | **Index only `knowledge/source/**`**; the research doc is not added. | 001, 004 |
