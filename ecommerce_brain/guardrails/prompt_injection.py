"""Prompt injection detector.

Implements a layered regex approach inspired by the PyConf Hyd 2026 workshop
(ORD-1006 payload demo). Checks both user queries and data returned by tools
before they enter the LLM context.
"""

from __future__ import annotations

import re

import structlog

log = structlog.get_logger(__name__)

# Ordered from most to least specific. First match wins.
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Direct instruction override — handles "ignore all previous instructions" etc.
    (r"ignore\s+(?:\w+\s+){0,3}instructions?", "ignore_instructions"),
    (r"(disregard|forget)\s+(your|the|all)\s+(instructions?|prompt|context|rules?)", "disregard_rules"),  # noqa: E501
    # Role hijacking — article is optional ("you are now DAN" has no article)
    (r"\byou\s+are\s+now\s+(?:(?:a|an|the)\s+)?\w+", "role_hijack"),
    (r"act\s+as\s+(if\s+you\s+are\s+)?(a|an|the)?\s*(different|new|unrestricted|uncensored|evil)", "act_as"),  # noqa: E501
    (r"\b(jailbreak|do\s+anything\s+now)\b", "jailbreak"),
    # System prompt leakage
    (r"reveal\s+(your|the)\s+(system\s+)?prompt", "prompt_leak"),
    (r"print\s+(your|the)\s+(system\s+|initial\s+)?instructions?", "prompt_leak"),
    (r"what\s+(is|are)\s+your\s+(instructions?|system\s+prompt|rules?)", "prompt_leak"),
    (r"(?:tell|show)\s+me\s+(?:your|the)\s+(?:instructions?|rules?|guidelines?|system\s+prompt)", "prompt_leak"),  # noqa: E501
    # Structural injection (delimiter attacks)
    (r"<\s*(system|assistant|user)\s*>", "delimiter_injection"),
    (r"\\n\\n(human|assistant|system)\s*:", "delimiter_injection"),
    (r"\]\]>|<!\[CDATA\[", "delimiter_injection"),
    (r"\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>", "model_token_injection"),
    # Context manipulation
    (r"(previous|above)\s+conversation\s+(was|is)\s+fake", "context_manipulation"),
    (r"override\s+(?:context|window|history|my\s+instructions?)", "context_manipulation"),
    (r"(translation|base64|rot13|encode|decode).{0,30}(instructions?|prompt)", "obfuscated_injection"),  # noqa: E501
]

_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), label)
    for p, label in _INJECTION_PATTERNS
]


class InjectionDetected(Exception):
    def __init__(self, pattern_label: str, matched_text: str) -> None:
        self.pattern_label = pattern_label
        self.matched_text = matched_text[:100]  # truncate for logging
        super().__init__(f"Prompt injection detected: {pattern_label}")


def check_for_injection(text: str, source: str = "user_input") -> bool:
    """Raise InjectionDetected if text contains a known injection pattern.

    Args:
        text: The string to check (user query OR tool-returned data).
        source: Label for logging (e.g., "user_input", "tool:get_order").

    Returns:
        True if input is clean (no injection detected).
    """
    for pattern, label in _COMPILED:
        match = pattern.search(text)
        if match:
            log.warning(
                "prompt_injection_blocked",
                source=source,
                pattern=label,
                snippet=text[:200],
            )
            raise InjectionDetected(label, match.group(0))
    return True


def sanitize_tool_output(text: str, tool_name: str) -> str:
    """Strip injection attempts from tool outputs before they enter LLM context.

    Rather than blocking (which would break the investigation), we strip the
    injected text and log a warning. Returns sanitized string.
    """
    sanitized = text
    for pattern, label in _COMPILED:
        if pattern.search(sanitized):
            log.warning(
                "injection_stripped_from_tool_output",
                tool=tool_name,
                pattern=label,
            )
            sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized
