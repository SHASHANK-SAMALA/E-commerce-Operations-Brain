"""Custom exception hierarchy for ecommerce_brain.

All application exceptions inherit from EcommerceBrainError so callers can
catch the whole family with a single clause when needed, while still being
able to distinguish specific failure modes with targeted except branches.
"""

from __future__ import annotations


class EcommerceBrainError(Exception):
    """Base class for all application-level exceptions."""


class ConfigurationError(EcommerceBrainError):
    """A required configuration value is missing or invalid."""


class DatabaseError(EcommerceBrainError):
    """A database operation failed."""


class MCPServerError(EcommerceBrainError):
    """An MCP tool server is unreachable or returned an unexpected error."""

    def __init__(self, domain: str, message: str) -> None:
        self.domain = domain
        super().__init__(f"MCP server for '{domain}' failed: {message}")


class AgentNotFoundError(EcommerceBrainError):
    """The agent registry contains no spec for the requested name."""

    def __init__(self, name: str, available: list[str] | None = None) -> None:
        self.name = name
        hint = f" Available: {available}" if available else ""
        super().__init__(f"No agent spec registered for '{name}'.{hint}")


class HITLStateError(EcommerceBrainError):
    """An invalid HITL state transition was attempted (e.g. resuming a non-pending investigation)."""


class RoutingError(EcommerceBrainError):
    """Query routing failed and cannot be recovered."""


class EmbeddingError(EcommerceBrainError):
    """Embedding generation failed and the caller cannot proceed without a vector."""
