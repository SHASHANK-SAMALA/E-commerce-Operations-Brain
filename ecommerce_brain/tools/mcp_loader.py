"""MCP tool loader — all tools are accessed exclusively through MCP servers.

Each domain agent connects to its dedicated MCP server (ports 8001-8005).
MCP servers must be running before starting the backend.
Start them with: python start_mcp_servers.py
"""

import asyncio

import httpcore
import httpx
import structlog

log = structlog.get_logger(__name__)

MCP_SERVERS = {
    "sales": "http://localhost:8001/sse",
    "inventory": "http://localhost:8002/sse",
    "marketing": "http://localhost:8003/sse",
    "support": "http://localhost:8004/sse",
    "action": "http://localhost:8005/sse",
}


def get_mcp_connections(agent_name: str) -> dict:
    """Return connections dict for MultiServerMCPClient."""
    if agent_name not in MCP_SERVERS:
        return {}
    return {f"{agent_name}_mcp": {"url": MCP_SERVERS[agent_name], "transport": "sse"}}


async def execute_mcp_tools_for_agent(agent_name: str) -> dict:
    """Execute all tools for an agent via its MCP server.

    Raises RuntimeError if the MCP server is unreachable — no local fallback.
    Returns {tool_name: result} dict.
    """
    if agent_name not in MCP_SERVERS:
        return {}

    from langchain_mcp_adapters.client import MultiServerMCPClient

    connections = {f"{agent_name}_mcp": {"url": MCP_SERVERS[agent_name], "transport": "sse"}}

    # langchain-mcp-adapters 0.2.x: do NOT use as context manager — instantiate directly
    client = MultiServerMCPClient(connections)
    tools = await client.get_tools()

    async def _invoke_one(tool) -> tuple[str, object]:
        try:
            result = await asyncio.wait_for(tool.ainvoke({}), timeout=30.0)
        except asyncio.TimeoutError:
            log.error("mcp_tool.timeout", agent=agent_name, tool=tool.name)
            result = {"error": f"tool '{tool.name}' timed out after 30s"}
        except (httpx.RemoteProtocolError, httpcore.RemoteProtocolError) as exc:
            log.error("mcp_tool.disconnected", agent=agent_name, tool=tool.name, error=str(exc)[:120])
            result = {"error": f"MCP server disconnected during '{tool.name}'"}
        except Exception as exc:
            result = {"error": str(exc)[:200]}
        return tool.name, result

    pairs = await asyncio.gather(*(_invoke_one(tool) for tool in tools))
    results = dict(pairs)

    log.info("mcp_tools.executed", agent=agent_name, tools=list(results.keys()))
    return results
