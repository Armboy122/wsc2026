# Contract

## Catalog and service

- `knowledge/source/` is the only factual source of truth; only approved local `.md` files are catalogued. Exclude symlinks, dotfiles, README files, and files resolving outside the configured root.
- Build a deterministic compact catalog at startup with relative POSIX `sourceId`, Markdown title, headings/topics, and approved deterministic alias metadata. Catalog generation performs no network/model calls.
- The ADK-facing Knowledge capability accepts selected `source_ids`; the server validates each ID against the catalog, rejects absolute paths, `..`, unknown IDs, duplicates, and requests exceeding the maximum document count.
- Return complete Markdown documents plus `sourceId`, title, and logical `knowledge://` URI provenance. Never summarize, generate answers, or silently truncate.
- If the total selected content exceeds the configured safe context budget, return a structured safe failure. Invalid/unknown IDs fail closed. Multiple approved documents may be fetched together.
- Knowledge code must not import or call `google.genai`, `generate_content`, OpenAI-compatible providers, or any generative provider/router/answer client.

## Testing Decisions

Test through the catalog/service public interfaces with temporary Markdown roots and a fake ADK tool boundary. Cover deterministic catalog metadata, alias validation, allowlisting, traversal/absolute paths, unknown IDs, full-file content, multi-document results, count/context limits, structured failure, and a static import/call assertion that Knowledge has no generative provider dependency. Run the full project suite after the vertical slice.
