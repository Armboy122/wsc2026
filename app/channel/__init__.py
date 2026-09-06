"""Shared channel layer for adapters, formatting, capabilities, and actions."""

from app.channel.actions import (
    ACTION_CONFIRM,
    ACTION_INTENT_PREFIX,
    ACTION_NEW_CHAT,
    ACTION_REJECT,
    format_actions,
    lookup_choice,
    parse_action_callback,
    register_choice,
)
from app.channel.capabilities import (
    CHANNEL_CAPABILITIES,
    ChannelCapabilities,
    get_channel_capabilities,
)
from app.channel.formatter import (
    SIMULATION_NOTICE,
    WELCOME_TEXT,
    degrade_for_channel,
    extract_citation_links,
    format_citations_text,
    split_text,
    truncate_button_label,
)

__all__ = [
    "ACTION_CONFIRM",
    "ACTION_INTENT_PREFIX",
    "ACTION_NEW_CHAT",
    "ACTION_REJECT",
    "CHANNEL_CAPABILITIES",
    "ChannelCapabilities",
    "SIMULATION_NOTICE",
    "WELCOME_TEXT",
    "degrade_for_channel",
    "extract_citation_links",
    "format_actions",
    "format_citations_text",
    "get_channel_capabilities",
    "lookup_choice",
    "parse_action_callback",
    "register_choice",
    "split_text",
    "truncate_button_label",
]
