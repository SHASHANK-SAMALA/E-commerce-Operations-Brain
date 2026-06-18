"""MCP tool loader — fresh SSE connection per call, no cache.

Each domain agent connects to its dedicated MCP server (ports 8001-8005).
MCP server URLs are configurable via environment variables (see settings.py)
so they resolve correctly both in local dev (localhost) and Docker (service names).
Start them locally with: python start_mcp_servers.py
"""

from __future__ import annotations

import structlog

from ecommerce_brain.config.settings import settings

log = structlog.get_logger(__name__)

MCP_SERVERS: dict[str, str] = {
    "sales":     settings.mcp_sales_url,
    "inventory": settings.mcp_inventory_url,
    "marketing": settings.mcp_marketing_url,
    "support":   settings.mcp_support_url,
    "action":    settings.mcp_action_url,
}


async def get_mcp_tools(agent_name: str) -> list:
    """Open a fresh SSE connection to the MCP server and return LangChain tools.

    No caching — each call opens and closes its own connection. This avoids
    stale connections when MCP servers restart.
    Raises RuntimeError if the MCP server is unreachable.
    """
    if agent_name not in MCP_SERVERS:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    url = MCP_SERVERS[agent_name]
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




