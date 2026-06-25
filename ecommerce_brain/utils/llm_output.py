"""Shared utilities for post-processing raw LLM text output."""

from __future__ import annotations


def strip_code_fence(raw: str) -> str:
    """Remove markdown triple-backtick fences from LLM output.

    Some models wrap JSON in ```json ... ``` blocks even when instructed not
    to. This strips the fence so downstream callers can reliably parse the
    content with json.loads.

    Args:
        raw: Raw text from an LLM response.

    Returns:
        The content inside the fence, or the original string if no fence is
        present.
    """
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n", 1)
    if len(lines) < 2:
        return stripped
    return lines[1].rsplit("```", 1)[0].strip()
