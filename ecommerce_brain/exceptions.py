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
    """A database operation failed.

    Raised when SQLAlchemy or the underlying DB driver reports an error so
    callers can distinguish database failures from other Exception types.
    """


class MCPServerError(EcommerceBrainError):
    """An MCP tool server is unreachable or returned an unexpected error.

    Args:
        domain: The agent domain key (e.g. "sales", "inventory").
        message: Human-readable failure description.
    """

    def __init__(self, domain: str, message: str) -> None:
        self.domain = domain
        super().__init__(f"MCP server for '{domain}' failed: {message}")


class AgentNotFoundError(EcommerceBrainError):
    """The agent registry contains no spec for the requested name.

    Args:
        name: The requested agent name.
        available: Optional list of known agent names for the error message.
    """

    def __init__(self, name: str, available: list[str] | None = None) -> None:
        self.name = name
        hint = f" Available: {available}" if available else ""
        super().__init__(f"No agent spec registered for '{name}'.{hint}")


class HITLStateError(EcommerceBrainError):
    """An invalid HITL state transition was attempted.

    Examples: resuming a non-pending investigation, approving an already-
    completed investigation.
    """


class RoutingError(EcommerceBrainError):
    """Query routing failed and cannot be recovered."""


class EmbeddingError(EcommerceBrainError):
    """Embedding generation failed and the caller cannot proceed without a vector."""


class MemoryWriteError(EcommerceBrainError):
    """One or more memory backends failed to persist the investigation.

    Raised (or used to tag audit log entries) when KEDB, incident store,
    or Mem0 writes fail, so the graph surface area can report the failure
    rather than silently completing with missing data.
    """


class StatusStoreError(EcommerceBrainError):
    """The status store (Redis or in-memory fallback) encountered an error."""


class LLMError(EcommerceBrainError):
    """An LLM API call failed (network error, timeout, or unexpected response)."""


class ToolExecutionError(EcommerceBrainError):
    """A tool invocation failed during action execution.

    Args:
        tool_name: Name of the tool that failed.
        message: Failure detail.
    """

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {message}")
