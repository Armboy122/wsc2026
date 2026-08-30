# Authoritative PEA Export Directory

This directory is the **only** part of the knowledge corpus that
`scripts/sync_knowledge.py` ever uploads to the Gemini File Search store.

Policy (safety-critical):

- Only **lead-approved, authoritative PEA exports** may be placed here.
- The repository intentionally ships **none**: this file is a non-factual
  placeholder, and no PEA rates, tiers, billing, payment, outage, or contact
  facts are bundled with the repo.
- No model-generated, sample, or demo "PEA" content may be added here.
  Enterprise facts must never come from model invention.
- This file is documentation, not knowledge content: it is excluded from
  sync like every `README.md` and metadata file.

Until a lead-approved export is added, a sync run over this tree uploads
nothing ("up to date; nothing to do"), and `knowledge_tool.search` returns
no evidence for questions the store does not cover.
