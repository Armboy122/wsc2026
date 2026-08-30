# PEA Knowledge Corpus

Corpus root for the Gemini File Search hosted-RAG store backing
`knowledge_tool` (Worker B — knowledge). The provider applies its **default
chunking** (no custom chunk size or overlap is ever sent by the sync script).

## Authoritative-source policy (safety-critical)

- The **only** files ever uploaded to the store are those under `source/`.
- `source/` may contain **only lead-approved, authoritative PEA exports**.
  The repository intentionally ships **none**: there are no sample, demo, or
  model-written PEA documents in this tree.
- Enterprise facts (electricity rates, tiers, billing, payment, outages,
  contacts) must never come from model invention. The previous bundled
  `docs/` sample corpus (including `pea-electricity-rates.md`) was removed
  because it contained unsourced enterprise facts.
- `knowledge/source/README.md` is a non-factual placeholder documenting this
  policy; like every `README.md` and metadata file, it is never uploaded.
- With no approved export in `source/`, a sync run is a no-op and
  `knowledge_tool.search` returns no citations for uncovered questions
  (fail-closed).

## Layout

```text
knowledge/
  README.md            this file (never uploaded)
  source/              the only uploadable subtree (lead-approved PEA exports)
    README.md          non-factual placeholder (never uploaded)
  manifest.json        SHA256 source manifest (generated, git-ignored)
  tests/               knowledge system tests (run: python3 -m pytest knowledge/tests)
```

## Configuration

| Variable | Meaning |
|---|---|
| `GEMINI_FILE_SEARCH_STORE` | File Search store resource name, e.g. `fileSearchStores/pea-knowledge` (create the store in Google AI Studio or via the API) |
| `GEMINI_API_KEY` | Google AI Studio API key (fallback: `GOOGLE_API_KEY`) |
| `GEMINI_FILE_SEARCH_MODEL` | Grounded-generation model (default `gemini-2.5-flash`) |

## Syncing

Run from the repository root (the `google-genai` SDK is only needed for real
uploads; `--dry-run` works without it):

```bash
pip install google-genai          # once, for real uploads

python3 scripts/sync_knowledge.py --dry-run          # show the plan only
python3 scripts/sync_knowledge.py                     # upload new/changed sources under source/ only
python3 scripts/sync_knowledge.py --file source/<approved-export>.md
python3 scripts/sync_knowledge.py --force             # re-upload unchanged sources as well
python3 scripts/sync_knowledge.py --prune --yes       # also delete removed sources
python3 scripts/sync_knowledge.py --root /path/to/export-corpus   # only /path/to/export-corpus/source/** is syncable
python3 scripts/sync_knowledge.py --dry-run --prune --yes --verbose
```

Behaviour:

- The default corpus root is `<repo>/knowledge`; the default manifest is
  `knowledge/manifest.json`. `--root` overrides the corpus root: the syncable
  subtree is `<root>/source/**` and the manifest defaults to
  `<root>/manifest.json`. A root without a `source/` directory is a usage
  error (exit 2), never a silent no-op.
- Only files under `source/` are syncable. `README.md` (any case, any depth),
  the manifest, hidden files, and files without a document suffix are never
  uploaded.
- A SHA256 manifest maps each corpus-relative path (e.g.
  `source/<export>.md`) to its content hash and the remote document name.
- Only **new** or **changed** sources are uploaded; unchanged files are left
  alone. `--force` re-uploads unchanged files as well.
- `--file PATH` limits a run to one (or more, repeated) exact corpus-relative
  path under `source/`; any other path is a usage error.
- Remote deletion happens **only** when both `--prune` and `--yes` are given;
  `--prune` without `--yes` prints a warning and deletes nothing. Entries from
  a previous (pre-repair) manifest that no longer resolve to a source file
  become prune candidates, so previously uploaded unsourced documents can be
  removed from the store with `--prune --yes`.
- Chunking always uses the provider default; the script never sends chunking
  configuration.

## Known limitations (2-day demo)

- Re-uploading a changed file creates a fresh remote document; the manifest
  tracks the latest document name, but older revisions may remain in the
  store until cleaned up in the provider console.
- Prune deletes by the manifest's stored document name; documents uploaded
  outside this script are not tracked and are never deleted.
