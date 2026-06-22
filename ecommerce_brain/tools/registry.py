"""Tool registry — @register_tool decorator auto-registers in global dict.

Per-agent whitelisting is enforced structurally:
  tools = [registry[name] for name in agent_spec.whitelisted_tools]
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, tool

registry: dict[str, BaseTool] = {}


def register_tool(func: Callable | None = None, **kwargs: Any) -> Callable:
    """Decorator — wraps with @tool and registers in global registry."""

    def decorator(f: Callable) -> Callable:
        wrapped: BaseTool = tool(f, **kwargs)
        if f.__name__ in registry:
            import warnings
            warnings.warn(
                f"Tool '{f.__name__}' is already registered — overwriting. "
                "Remove the duplicate @register_tool declaration.",
                stacklevel=3,
            )
        registry[f.__name__] = wrapped
        # Return the original function so importing modules receive a callable
        # (MCP servers expect to import the real function, not the wrapped tool)
        return f

    if func is not None:
        return decorator(func)
    return decorator
