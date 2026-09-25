"""Deterministic query expansion from maintainer-authored alias rules.

No model, no synonyms database: if a normalized alias trigger is contained in the normalized
query, the rule's alias terms are appended to the query before BM25/embedding scoring.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.knowledge.aliases import KnowledgeAliasRule, normalize_alias


def expand_query(query: str, rules: Sequence[KnowledgeAliasRule]) -> tuple[str, ...]:
    """Return alias terms to append, in rule order, deduplicated and stable."""
    normalized = normalize_alias(query)
    if not normalized:
        return ()
    extra: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if not any(normalize_alias(alias) in normalized for alias in rule.aliases):
            continue
        for alias in rule.aliases:
            key = normalize_alias(alias)
            if key and key not in seen:
                seen.add(key)
                extra.append(alias)
    return tuple(extra)
