"""LangGraph StateGraph assembly — the full E-Commerce Brain graph.

Topology:
  guardrail → coordinator → memory_recall → fanout(domain agents) →
  reflection → synthesis → hitl → action_executor → memory_writer

PostgresSaver checkpointer enables:
  - State persistence across server restarts
  - HITL interrupt/resume via thread_id
  - Full execution history
"""

from __future__ import annotations

import os
import uuid
import warnings
from contextlib import asynccontextmanager
from typing import Any

# Suppress LangGraph msgpack warnings for our own Pydantic types — must be set before langgraph import.
os.environ.setdefault(
    "LANGGRAPH_ALLOWED_MSGPACK_MODULES",
    "ecommerce_brain.schemas.outputs,ecommerce_brain.schemas.routing,ecommerce_brain.schemas.memory",
)
warnings.filterwarnings(
    "ignore",
    message="Deserializing unregistered type",
    category=UserWarning,
)

import psycopg
import structlog
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ecommerce_brain.graph.nodes.action_executor import action_executor_node
from ecommerce_brain.graph.nodes.coordinator import coordinator_node
from ecommerce_brain.graph.nodes.domain_agents import (
    inventory_agent_node,
    marketing_agent_node,
    sales_agent_node,
    support_agent_node,
)
from ecommerce_brain.graph.nodes.guardrail import guardrail_node
from ecommerce_brain.graph.nodes.hitl import hitl_node
from ecommerce_brain.graph.nodes.memory_answer import memory_answer_node
from ecommerce_brain.graph.nodes.memory_recall import memory_recall_node
from ecommerce_brain.graph.nodes.memory_writer import memory_writer_node
from ecommerce_brain.graph.nodes.reflection import reflection_node
from ecommerce_brain.graph.nodes.synthesis import synthesis_node
from ecommerce_brain.graph.state import GraphState

log = structlog.get_logger(__name__)

_DOMAIN_NODE_MAP: dict[str, str] = {
    "sales": "sales_agent",
    "inventory": "inventory_agent",
    "marketing": "marketing_agent",
    "support": "support_agent",
}


# Edge conditions

def _guardrail_edge(state: GraphState) -> str:
    if state.get("blocked_reason") or state.get("error"):
        return "blocked"
    return "ok"


def _fanout_edge(state: GraphState) -> list[Send]:
    """Level-1 parallelism: dispatch only required domains."""
    domains = state.get("domains_required", [])
    sends = []
    for domain in domains:
        node = _DOMAIN_NODE_MAP.get(domain)
        if node:
            sends.append(Send(node, state))
    return sends if sends else [Send("reflection", state)]


def _after_memory_recall_edge(state: GraphState):
    """Route memory_query intent to memory_answer node; all others fan out to domain agents."""
    if state.get("intent") == "memory_query":
        return "memory_answer"
    return _fanout_edge(state)


def _reflection_edge(state: GraphState) -> str:
    result = state.get("reflection_result")
    if result and result.should_reinvestigate:
        return "reinvestigate"
    return "synthesize"


def _hitl_edge(state: GraphState) -> str:
    if state.get("skip_hitl"):
        return "execute"
    if state.get("hitl_status") == "rejected":
        return "rejected"
    return "execute"


# Graph builder

def build_graph(checkpointer=None) -> Any:
    builder = StateGraph(GraphState)

    # Nodes
    builder.add_node("guardrail", guardrail_node)
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("memory_recall", memory_recall_node)
    builder.add_node("memory_answer", memory_answer_node)
    builder.add_node("sales_agent", sales_agent_node)
    builder.add_node("inventory_agent", inventory_agent_node)
    builder.add_node("marketing_agent", marketing_agent_node)
    builder.add_node("support_agent", support_agent_node)
    builder.add_node("reflection", reflection_node)
    builder.add_node("synthesis", synthesis_node)
    builder.add_node("hitl", hitl_node)
    builder.add_node("action_executor", action_executor_node)
    builder.add_node("memory_writer", memory_writer_node)

    # Edges
    builder.add_edge(START, "guardrail")
    builder.add_conditional_edges(
        "guardrail",
        _guardrail_edge,
        {"ok": "coordinator", "blocked": END},
    )
    builder.add_edge("coordinator", "memory_recall")
    builder.add_conditional_edges(
        "memory_recall",
        _after_memory_recall_edge,
        _DOMAIN_NODE_MAP | {"reflection": "reflection", "memory_answer": "memory_answer"},
    )
    # memory_answer skips domain agents, reflection, synthesis, and HITL
    builder.add_edge("memory_answer", "memory_writer")

    # Fan-in: all domain agents → reflection
    for node in _DOMAIN_NODE_MAP.values():
        builder.add_edge(node, "reflection")

    builder.add_conditional_edges(
        "reflection",
        _reflection_edge,
        {"reinvestigate": "coordinator", "synthesize": "synthesis"},
    )
    builder.add_edge("synthesis", "hitl")
    builder.add_conditional_edges(
        "hitl",
        _hitl_edge,
        {"execute": "action_executor", "rejected": "memory_writer"},
    )
    builder.add_edge("action_executor", "memory_writer")
    builder.add_edge("memory_writer", END)

    return builder.compile(checkpointer=checkpointer)


def get_checkpointer():
    """Create a PostgresSaver checkpointer for HITL state persistence.

    The connection is owned by the returned saver.  Callers that need a bounded
    lifetime should use ``get_async_checkpointer()`` instead, which is a proper
    async context manager that closes the connection on exit.

    Note: this synchronous variant is intended for use during application
    startup (e.g. in ``get_graph(with_checkpointer=True)``).  Long-lived
    processes should use the async variant via the lifespan context.
    """
    from ecommerce_brain.config.settings import get_settings
    conn = psycopg.connect(get_settings().database_url, autocommit=True)
    saver = PostgresSaver(conn)
    saver.setup()
    return saver

@asynccontextmanager
async def get_async_checkpointer():
    """Async context manager that yields a ready AsyncPostgresSaver.

    Use this inside FastAPI lifespan or background tasks — it closes the
    underlying connection cleanly on exit.
    """
    from ecommerce_brain.config.settings import get_settings
    async with AsyncPostgresSaver.from_conn_string(get_settings().database_url) as saver:
        await saver.setup()
        yield saver

# Module-level graph instance (no checkpointer — for testing/dev without Postgres)
_graph_no_checkpoint = None
_graph_with_checkpoint = None


def get_graph(with_checkpointer: bool = False, checkpointer: Any = None):
    """Factory to return the compiled LangGraph state machine.

    Args:
        with_checkpointer: If True, attach a default synchronous Postgres saver.
        checkpointer: Custom checkpointer (e.g. AsyncPostgresSaver). Overrides with_checkpointer.
    """
    if checkpointer is not None:
        return build_graph(checkpointer)

    if with_checkpointer:
        global _graph_with_checkpoint
        if _graph_with_checkpoint is None:
            _graph_with_checkpoint = build_graph(get_checkpointer())
        return _graph_with_checkpoint

    global _graph_no_checkpoint
    if _graph_no_checkpoint is None:
        _graph_no_checkpoint = build_graph()
    return _graph_no_checkpoint


def new_investigation_id() -> str:
    return f"inv-{uuid.uuid4().hex[:12]}"
