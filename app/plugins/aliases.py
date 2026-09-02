"""Plugin-local Markdown routing aliases compiled into safe LLM catalogue guidance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ALIAS_FILENAME = "aliases.md"
_FRONT_MATTER = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)


class PluginAliasError(ValueError):
    """A plugin's human-edited routing aliases are invalid or ambiguous."""


@dataclass(frozen=True, slots=True)
class PluginAliasRule:
    """Phrases that indicate one LLM-exposed action of an operational plugin."""

    action: str
    phrases: tuple[str, ...]


def load_alias_guidance(plugin_directory: Path, allowed_actions: set[str]) -> str:
    """Read one optional ``aliases.md`` file and render trusted compact planner guidance."""
    path = plugin_directory / _ALIAS_FILENAME
    if not path.exists():
        return ""
    if not path.is_file() or path.is_symlink():
        raise PluginAliasError(f"plugin alias file is not a regular file: {path.name}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PluginAliasError(f"cannot read plugin alias file: {path.name}") from exc
    match = _FRONT_MATTER.match(content)
    if match is None:
        raise PluginAliasError(f"plugin alias file requires YAML front matter: {path.name}")
    try:
        raw = yaml.safe_load(match.group("body"))
    except yaml.YAMLError as exc:
        raise PluginAliasError(f"plugin alias file has invalid YAML: {path.name}") from exc
    rules = _validate_rules(raw, allowed_actions, path.name)
    return "Routing aliases: " + "; ".join(
        f"when the user says {', '.join(repr(phrase) for phrase in rule.phrases)}, prefer {rule.action}"
        for rule in rules
    )


def _validate_rules(
    raw: Any, allowed_actions: set[str], filename: str
) -> tuple[PluginAliasRule, ...]:
    if not isinstance(raw, dict) or set(raw) != {"rules"}:
        raise PluginAliasError(f"plugin alias file supports only a rules list: {filename}")
    items = raw.get("rules")
    if not isinstance(items, list) or not items:
        raise PluginAliasError(f"plugin alias file needs at least one rule: {filename}")

    rules: list[PluginAliasRule] = []
    seen_phrases: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"action", "phrases"}:
            raise PluginAliasError(f"plugin alias rule is invalid: {filename}")
        action, phrases = item["action"], item["phrases"]
        if not isinstance(action, str) or action not in allowed_actions:
            raise PluginAliasError(f"plugin alias rule uses unavailable action: {filename}")
        if (
            not isinstance(phrases, list)
            or not phrases
            or any(not isinstance(phrase, str) or not phrase.strip() for phrase in phrases)
        ):
            raise PluginAliasError(f"plugin alias rule needs non-empty phrases: {filename}")
        normalized = [" ".join(phrase.casefold().split()) for phrase in phrases]
        if len(set(normalized)) != len(normalized) or any(
            phrase in seen_phrases for phrase in normalized
        ):
            raise PluginAliasError(f"plugin alias phrase is duplicated: {filename}")
        seen_phrases.update(normalized)
        rules.append(PluginAliasRule(action, tuple(" ".join(phrase.split()) for phrase in phrases)))
    return tuple(rules)
