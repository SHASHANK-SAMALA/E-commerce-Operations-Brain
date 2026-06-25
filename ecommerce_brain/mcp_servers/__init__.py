"""MCP server entry points — one FastMCP server per domain agent.

Each server exposes its domain tools over SSE transport so LangChain
MCP adapters can load them at agent startup.
"""
