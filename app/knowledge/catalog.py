"""Deterministic allowlist of approved local Markdown knowledge documents.

Catalog construction is offline and deterministic: it reads approved files under one
configured source root and derives a title from the Markdown itself. It never calls a model,
embedding service, or network.

The catalog is the only allowlist for Knowledge source IDs. Anything that is not an approved
local Markdown file inside the root is absent from it and therefore cannot enter the index.
Symlinks, dot-prefixed paths, ``README.md`` files, and paths whose resolution escapes the root
are excluded. Alias configuration is validated here as well; the index loads the same rules for
query expansion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.knowledge.aliases import load_alias_rules

APPROVED_SUFFIX = ".md"
_DEFAULT_ALIAS_DIRNAME = "aliases"

_TITLE_HEADING_LEVEL = 1
_HEADING = re.compile(r"^(?P<level>#{1,6})[ \t]+(?P<text>.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")


@dataclass(frozen=True)
class KnowledgeDocument:
    """One approved document, addressed by its root-relative POSIX source ID."""

    source_id: str
    path: Path
    title: str


class KnowledgeCatalog:
    """Immutable, deterministically ordered allowlist of one approved source root."""

    def __init__(
        self,
        source_root: Path | str,
        alias_root: Path | str | None = None,
    ) -> None:
        self._source_root = Path(source_root)
        alias_path = (
            Path(alias_root)
            if alias_root is not None
            else self._source_root.parent / _DEFAULT_ALIAS_DIRNAME
        )
        documents = self._build_documents()
        if self._source_root.is_dir():
            # Fail fast on invalid alias configuration; the index loads the rules itself.
            load_alias_rules(alias_path, {document.source_id for document in documents})
        self._documents: tuple[KnowledgeDocument, ...] = tuple(documents)
        self._by_id: dict[str, KnowledgeDocument] = {
            document.source_id: document for document in self._documents
        }

    @property
    def source_root(self) -> Path:
        return self._source_root

    @property
    def documents(self) -> tuple[KnowledgeDocument, ...]:
        """Approved documents, ordered by source ID for reproducible builds."""
        return self._documents

    def get(self, source_id: str) -> KnowledgeDocument | None:
        return self._by_id.get(source_id)

    def __len__(self) -> int:
        return len(self._documents)

    def __contains__(self, source_id: object) -> bool:
        return isinstance(source_id, str) and source_id in self._by_id

    def _build_documents(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        for source_id, path in sorted(self._approved_files()):
            try:
                title = _read_markdown_title(path)
            except (OSError, UnicodeError):
                # An unreadable approved file must not remove the rest of the allowlist.
                continue
            documents.append(KnowledgeDocument(source_id=source_id, path=path, title=title))
        return documents

    def _approved_files(self) -> list[tuple[str, Path]]:
        root = self._source_root
        if not root.is_dir():
            return []
        resolved_root = root.resolve()
        approved: list[tuple[str, Path]] = []
        for candidate in root.rglob("*"):
            if candidate.suffix.lower() != APPROVED_SUFFIX:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                continue
            relative = candidate.relative_to(root)
            if _is_excluded_relative_path(relative):
                continue
            if not candidate.resolve().is_relative_to(resolved_root):
                continue
            approved.append((relative.as_posix(), candidate))
        return approved


def _is_excluded_relative_path(relative: Path) -> bool:
    if relative.name.lower() == "readme.md":
        return True
    return any(part.startswith(".") for part in relative.parts)


def _read_markdown_title(path: Path) -> str:
    """Derive a title from the first Markdown heading without a model or interpretation."""
    text = path.read_text(encoding="utf-8")
    in_fence = False
    fallback: str | None = None
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match is None:
            continue
        heading = match.group("text").strip()
        if not heading:
            continue
        if len(match.group("level")) == _TITLE_HEADING_LEVEL:
            return heading
        if fallback is None:
            fallback = heading
    return fallback or path.stem
