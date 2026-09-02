"""Validated, deterministic aliases for routing approved knowledge documents.

Alias rules are Markdown configuration outside ``knowledge/source``.  They can improve
routing but can never provide facts: a matching rule selects already-approved source
files, which are still read in full and cited by the normal knowledge backend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_RULE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_FRONT_MATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)


@dataclass(frozen=True)
class KnowledgeAliasRule:
    """One maintainer-authored mapping from user phrases to approved source IDs."""

    rule_id: str
    aliases: tuple[str, ...]
    source_ids: tuple[str, ...]


def normalize_alias(value: str) -> str:
    """Normalize only case and whitespace so matching remains explicit and predictable."""
    return " ".join(value.casefold().split())


def load_alias_rules(alias_root: Path, known_source_ids: set[str]) -> tuple[KnowledgeAliasRule, ...]:
    """Load strict Markdown front matter and reject unsafe or ambiguous configuration."""
    if not alias_root.exists():
        return ()
    if not alias_root.is_dir():
        raise ValueError(f"knowledge alias path is not a directory: {alias_root}")

    rules: list[KnowledgeAliasRule] = []
    seen_rule_ids: set[str] = set()
    seen_aliases: set[str] = set()
    for path in sorted(alias_root.glob("*.md")):
        if path.is_symlink() or path.name.lower() == "readme.md":
            continue
        rule = _parse_rule(path)
        if rule.rule_id in seen_rule_ids:
            raise ValueError(f"duplicate knowledge alias rule id: {rule.rule_id}")
        if missing := set(rule.source_ids) - known_source_ids:
            raise ValueError(
                f"knowledge alias rule {rule.rule_id} references unknown source IDs: "
                + ", ".join(sorted(missing))
            )
        normalized_aliases = [normalize_alias(alias) for alias in rule.aliases]
        if any(alias in seen_aliases for alias in normalized_aliases):
            raise ValueError(f"duplicate knowledge alias in rule: {rule.rule_id}")
        seen_rule_ids.add(rule.rule_id)
        seen_aliases.update(normalized_aliases)
        rules.append(rule)
    return tuple(rules)


def matching_rule(query: str, rules: tuple[KnowledgeAliasRule, ...]) -> KnowledgeAliasRule | None:
    """Return the rule with the most specific explicit phrase contained in the query."""
    normalized_query = normalize_alias(query)
    matches = [
        (len(normalize_alias(alias)), rule)
        for rule in rules
        for alias in rule.aliases
        if normalize_alias(alias) in normalized_query
    ]
    if not matches:
        return None
    # Duplicate normalized aliases are rejected at load time; ID makes remaining ties stable.
    return max(matches, key=lambda item: (item[0], item[1].rule_id))[1]


def _parse_rule(path: Path) -> KnowledgeAliasRule:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read knowledge alias rule: {path.name}") from exc
    match = _FRONT_MATTER.match(content)
    if match is None:
        raise ValueError(f"knowledge alias rule requires front matter: {path.name}")
    data = _parse_front_matter(match.group("body"), path.name)
    if set(data) != {"id", "aliases", "sourceIds"}:
        raise ValueError(f"knowledge alias rule has unsupported fields: {path.name}")
    rule_id = data["id"]
    aliases = data["aliases"]
    source_ids = data["sourceIds"]
    if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
        raise ValueError(f"knowledge alias rule has invalid id: {path.name}")
    if not aliases or not source_ids:
        raise ValueError(f"knowledge alias rule needs aliases and sourceIds: {path.name}")
    if len(set(aliases)) != len(aliases) or any(not alias.strip() for alias in aliases):
        raise ValueError(f"knowledge alias rule has duplicate or blank aliases: {path.name}")
    if len(set(source_ids)) != len(source_ids) or any(not source_id.strip() for source_id in source_ids):
        raise ValueError(f"knowledge alias rule has duplicate or blank source IDs: {path.name}")
    return KnowledgeAliasRule(rule_id, tuple(aliases), tuple(source_ids))


def _parse_front_matter(body: str, filename: str) -> dict[str, str | list[str]]:
    """Parse the deliberately small YAML subset used by human-edited rule files."""
    data: dict[str, str | list[str]] = {}
    current_list: list[str] | None = None
    for raw_line in body.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("  - ") and current_list is not None:
            value = raw_line[4:].strip()
            if not value:
                raise ValueError(f"knowledge alias rule has blank list item: {filename}")
            current_list.append(value)
            continue
        if raw_line.startswith("-") or raw_line[:1].isspace() or ":" not in raw_line:
            raise ValueError(f"knowledge alias rule has invalid front matter: {filename}")
        key, value = raw_line.split(":", 1)
        if key in data:
            raise ValueError(f"knowledge alias rule repeats field {key}: {filename}")
        value = value.strip()
        if value:
            data[key] = value
            current_list = None
        else:
            current_list = []
            data[key] = current_list
    if not isinstance(data.get("id"), str):
        raise ValueError(f"knowledge alias rule needs id: {filename}")
    for key in ("aliases", "sourceIds"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"knowledge alias rule needs a {key} list: {filename}")
    return data
