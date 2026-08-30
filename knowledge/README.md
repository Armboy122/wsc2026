# PEA Knowledge Corpus

Demo corpus for the Gemini File Search hosted-RAG store backing
`knowledge_tool` (Worker B — knowledge). Documents are plain text/Markdown so
the store stays easy to curate; the provider applies its **default chunking**
(no custom chunk size or overlap is ever sent by the sync script).

> The documents in `docs/` are **sample demo content** written for the PEA
> One Agent competition. They are not official PEA publications.

## Layout

```text
knowledge/
  README.md            this file
  docs/                corpus sources (synced to the store)
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
python3 scripts/sync_knowledge.py                     # upload new/changed only
python3 scripts/sync_knowledge.py --file docs/pea-electricity-rates.md
python3 scripts/sync_knowledge.py --force             # re-upload everything
python3 scripts/sync_knowledge.py --prune --yes       # also delete removed sources
python3 scripts/sync_knowledge.py --dry-run --prune --yes --verbose
```

Behaviour:

- A SHA256 manifest (`knowledge/manifest.json`) maps each corpus-relative
  path to its content hash and the remote document name.
- The corpus-root `README.md` is documentation and is **not** synced; only
  knowledge content under the tree (e.g. `docs/`) is uploaded.
- Only **new** or **changed** sources are uploaded; unchanged files are left
  alone. `--force` re-uploads unchanged files as well.
- `--file PATH` limits a run to one (or more, repeated) corpus-relative path.
- Remote deletion happens **only** when both `--prune` and `--yes` are given;
  `--prune` without `--yes` prints a warning and deletes nothing.
- Chunking always uses the provider default; the script never sends chunking
  configuration.

## Known limitations (2-day demo)

- Re-uploading a changed file creates a fresh remote document; the manifest
  tracks the latest document name, but older revisions may remain in the
  store until cleaned up in the provider console.
- Prune deletes by the manifest's stored document name; documents uploaded
  outside this script are not tracked and are never deleted.
