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

# Per-agent cache of (client, tools). Built lazily on first use, reused after.
_tools_cache: dict[str, list] = {}
_cache_lock = asyncio.Lock()


def get_mcp_connections(agent_name: str) -> dict:
    """Return connections dict for MultiServerMCPClient."""
    if agent_name not in MCP_SERVERS:
        return {}
    return {f"{agent_name}_mcp": {"url": MCP_SERVERS[agent_name], "transport": "sse"}}


async def get_mcp_tools(agent_name: str):
    """Return LangChain tool objects from the MCP server WITHOUT executing them.

    Tools are cached per agent so we don't reopen an SSE connection on every
    domain-agent invocation. Raises RuntimeError if the MCP server is unreachable.
    """
    if agent_name not in MCP_SERVERS:
        return []

    if agent_name in _tools_cache:
        return _tools_cache[agent_name]

    async with _cache_lock:
        if agent_name in _tools_cache:
            return _tools_cache[agent_name]

        from langchain_mcp_adapters.client import MultiServerMCPClient

        connections = {f"{agent_name}_mcp": {"url": MCP_SERVERS[agent_name], "transport": "sse"}}
        client = MultiServerMCPClient(connections)
        tools = await client.get_tools()
        _tools_cache[agent_name] = tools
        log.info("mcp_tools.loaded", agent=agent_name, tools=[t.name for t in tools])
        return tools


def reset_mcp_tools_cache() -> None:
    """Drop the cached tools — useful for tests or when MCP servers restart."""
    _tools_cache.clear()


async def execute_mcp_tool(tool, arguments: dict, agent_name: str):
    """Execute a single MCP tool with the given arguments.

    Used by the agent loop after the LLM decides which tool to call.
    """
    try:
        result = await asyncio.wait_for(tool.ainvoke(arguments), timeout=30.0)
        return result
    except TimeoutError:
        log.error("mcp_tool.timeout", agent=agent_name, tool=tool.name)
        return {"error": f"tool '{tool.name}' timed out after 30s"}
    except (httpx.RemoteProtocolError, httpcore.RemoteProtocolError) as exc:
        log.error("mcp_tool.disconnected", agent=agent_name, tool=tool.name, error=str(exc)[:120])
        return {"error": f"MCP server disconnected during '{tool.name}'"}
    except Exception as exc:
        return {"error": str(exc)[:200]}


async def execute_mcp_tools_for_agent(agent_name: str) -> dict:
    """DEPRECATED: blind pre-fetch — kept only for backwards compat during transition.

    Prefer the bind_tools agent pattern in domain_agents.py instead.
    """
    tools = await get_mcp_tools(agent_name)

    async def _invoke_one(tool) -> tuple[str, object]:
        return tool.name, await execute_mcp_tool(tool, {}, agent_name)

    pairs = await asyncio.gather(*(_invoke_one(tool) for tool in tools))
    results = dict(pairs)
    log.info("mcp_tools.executed", agent=agent_name, tools=list(results.keys()))
    return results
