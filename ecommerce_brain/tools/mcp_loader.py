"""MCP tool loader — fresh SSE connection per call.

Each domain agent connects to its dedicated MCP server (ports 8001-8005).
MCP server URLs are read lazily from settings so importing this module in
test environments without a .env file does not raise a validation error.

Start locally (non-Docker): python start_mcp_servers.py
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

_DOMAIN_URL_KEYS = {
    "sales": "mcp_sales_url",
    "inventory": "mcp_inventory_url",
    "marketing": "mcp_marketing_url",
    "support": "mcp_support_url",
    "action": "mcp_action_url",
}


def _get_server_url(agent_name: str) -> str | None:
    """Resolve the MCP server URL for *agent_name* from settings at call time."""
    key = _DOMAIN_URL_KEYS.get(agent_name)
    if key is None:
        return None
    from ecommerce_brain.config.settings import get_settings

    return getattr(get_settings(), key, None)


async def get_mcp_tools(agent_name: str) -> list:
    """Open a fresh SSE connection to the MCP server and return LangChain tools.

    No connection caching — each call opens and closes its own connection so
    MCP server restarts are transparent to the agent.

    Args:
        agent_name: Domain key — one of "sales", "inventory", "marketing",
                    "support", "action".

    Returns:
        List of LangChain-compatible tool objects from the MCP server.

    Raises:
        RuntimeError: If the MCP server is unreachable.
    """
    url = _get_server_url(agent_name)
    if url is None:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    connections = {f"{agent_name}_mcp": {"url": url, "transport": "sse"}}
    try:
        client = MultiServerMCPClient(connections)
        tools = await client.get_tools()
        log.info("mcp_tools.loaded", agent=agent_name, tools=[t.name for t in tools])
        return tools
    except Exception as exc:
        raise RuntimeError(
            f"MCP server for '{agent_name}' is unreachable ({url}). "
            f"Start it with: python start_mcp_servers.py\nDetail: {exc!s}"
        ) from exc




