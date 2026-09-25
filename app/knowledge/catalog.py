"""Deterministic catalog of approved local Markdown knowledge documents.

Catalog construction is offline and deterministic: it reads approved files under one
configured source root, derives metadata from the Markdown itself, and attaches
maintainer-approved alias phrases. It never calls a model, embedding service, or network.

The catalog is the only allowlist for Knowledge source IDs. Anything that is not an
approved local Markdown file inside the root is absent from it and therefore cannot be
selected. Symlinks, dot-prefixed paths, ``README.md`` files, and paths whose resolution
escapes the root are excluded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.backends.knowledge_aliases import load_alias_rules

APPROVED_SUFFIX = ".md"
MAX_CATALOG_HEADINGS = 12
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
    headings: tuple[str, ...]
    aliases: tuple[str, ...] = ()

    def as_catalog_entry(self) -> dict[str, object]:
        """Compact model-facing metadata: identifiers and topics, never document content."""
        entry: dict[str, object] = {
            "sourceId": self.source_id,
            "title": self.title,
            "headings": list(self.headings[:MAX_CATALOG_HEADINGS]),
        }
        if self.aliases:
            entry["aliases"] = list(self.aliases)
        return entry


class KnowledgeCatalog:
    """Immutable, deterministically ordered view of one approved source root."""

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
        aliases = self._build_aliases(alias_path, {document.source_id for document in documents})
        self._documents: tuple[KnowledgeDocument, ...] = tuple(
            KnowledgeDocument(
                source_id=document.source_id,
                path=document.path,
                title=document.title,
                headings=document.headings,
                aliases=aliases.get(document.source_id, ()),
            )
            for document in documents
        )
        self._by_id: dict[str, KnowledgeDocument] = {
            document.source_id: document for document in self._documents
        }

    @property
    def source_root(self) -> Path:
        return self._source_root

    @property
    def documents(self) -> tuple[KnowledgeDocument, ...]:
        """Approved documents, ordered by source ID for reproducible catalogs."""
        return self._documents

    def get(self, source_id: str) -> KnowledgeDocument | None:
        return self._by_id.get(source_id)

    def entries(self) -> tuple[dict[str, object], ...]:
        return tuple(document.as_catalog_entry() for document in self._documents)

    def __len__(self) -> int:
        return len(self._documents)

    def __contains__(self, source_id: object) -> bool:
        return isinstance(source_id, str) and source_id in self._by_id

    def _build_documents(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        for source_id, path in sorted(self._approved_files()):
            try:
                title, headings = _read_markdown_metadata(path)
            except (OSError, UnicodeError):
                # An unreadable approved file must not remove the rest of the catalog.
                continue
            documents.append(
                KnowledgeDocument(
                    source_id=source_id, path=path, title=title, headings=headings
                )
            )
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

    def _build_aliases(
        self, alias_root: Path, known_source_ids: set[str]
    ) -> dict[str, tuple[str, ...]]:
        if not self._source_root.is_dir():
            return {}
        aliases: dict[str, list[str]] = {}
        for rule in load_alias_rules(alias_root, known_source_ids):
            for source_id in rule.source_ids:
                bucket = aliases.setdefault(source_id, [])
                for alias in rule.aliases:
                    if alias not in bucket:
                        bucket.append(alias)
        return {source_id: tuple(values) for source_id, values in aliases.items()}


def _is_excluded_relative_path(relative: Path) -> bool:
    if relative.name.lower() == "readme.md":
        return True
    return any(part.startswith(".") for part in relative.parts)


def _read_markdown_metadata(path: Path) -> tuple[str, tuple[str, ...]]:
    """Derive title and headings from Markdown text without a model or interpretation."""
    text = path.read_text(encoding="utf-8")
    headings: list[str] = []
    in_fence = False
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
        if heading and heading not in headings:
            headings.append(heading)
    level_one = next(
        (
            match.group("text").strip()
            for line in text.splitlines()
            if not _FENCE.match(line)
            and (match := _HEADING.match(line)) is not None
            and len(match.group("level")) == _TITLE_HEADING_LEVEL
        ),
        None,
    )
    title = level_one or (headings[0] if headings else path.stem)
    return title, tuple(headings)
