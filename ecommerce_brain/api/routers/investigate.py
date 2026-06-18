"""Investigation router — start investigation, poll status, stream via SSE, resume after HITL."""

from __future__ import annotations

import asyncio
import json
import time

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ecommerce_brain.api.deps import require_api_key
from ecommerce_brain.api.status_store import get_status, set_status, update_status
from ecommerce_brain.graph.graph import (
    get_async_checkpointer,  # noqa: E402
    get_graph,
    new_investigation_id,
)
from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.guardrails.prompt_injection import InjectionDetected, check_for_injection
from ecommerce_brain.schemas.inputs import HITLDecision, InvestigateRequest

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/investigate", tags=["investigate"])


async def _run_investigation(query_id: str, thread_id: str, initial_state: dict):
    """Run the graph in background — updates status store as it progresses."""
    try:
        async with get_async_checkpointer() as checkpointer:
            graph = get_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}, "callbacks": []}

            async for event in graph.astream(initial_state, config=config):
                node = list(event.keys())[0]
                log.info("graph.event", node=node, query_id=query_id)

                node_state = event.get(node, {})
                if isinstance(node_state, dict) and node_state.get("blocked_reason"):
                    set_status(query_id, {
                        "status": "blocked",
                        "thread_id": thread_id,
                        "error": node_state.get("error"),
                    })
                    return

            state = await graph.aget_state(config)
            current_state = state.values

        if current_state.get("hitl_status") == "pending_approval" or state.next:
            set_status(query_id, {
                "status": "pending_approval",
                "thread_id": thread_id,
                "proposed_actions": current_state.get("proposed_actions", []),
                "root_cause_summary": (
                    current_state["root_cause_report"].summary
                    if current_state.get("root_cause_report")
                    else ""
                ),
                "audit_log": current_state.get("audit_log", []),
            })
        elif current_state.get("error"):
            update_status(query_id, {
                "status": "error",
                "error": current_state["error"],
                "audit_log": current_state.get("audit_log", []),
            })
        else:
            domain_reports = {}
            for key in ("sales_report", "inventory_report", "marketing_report", "support_report"):
                rpt = current_state.get(key)
                if rpt is not None:
                    domain_reports[key] = rpt.model_dump()

            update_status(query_id, {
                "status": "completed",
                "result": (
                    current_state["root_cause_report"].model_dump()
                    if current_state.get("root_cause_report")
                    else None
                ),
                "domain_reports": domain_reports,
                "audit_log": current_state.get("audit_log", []),
            })

    except Exception as exc:
        log.error("investigation.failed", query_id=query_id, error=repr(exc))
        set_status(query_id, {
            "status": "error",
            "thread_id": thread_id,
            "error": repr(exc)[:500],
        })


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def start_investigation(
    req: InvestigateRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_api_key),
):
    """Start an investigation. Returns query_id immediately for polling."""
    try:
        check_for_injection(req.query, source="api_input")
    except InjectionDetected as e:
        raise HTTPException(status_code=400, detail=f"Input blocked: {e.pattern_label}") from e

    query_id = new_investigation_id()
    thread_id = f"thread-{query_id}"

    initial_state: GraphState = {
        "query": req.query,
        "query_id": query_id,
        "session_id": req.session_id,
        "routing_decision": None,
        "intent": None,
        "domains_required": [],
        "routing_confidence": 0.0,
        "memory_context": None,
        "sales_report": None,
        "inventory_report": None,
        "marketing_report": None,
        "support_report": None,
        "reflection_result": None,
        "loop_count": 0,
        "root_cause_report": None,
        "proposed_actions": [],
        "hitl_status": "pending",
        "approved_actions": [],
        "execution_results": [],
        "total_tokens": 0,
        "investigation_start_ms": int(time.time() * 1000),
        "error": None,
        "blocked_reason": None,
        "audit_log": [],
    }

    set_status(query_id, {"status": "running", "thread_id": thread_id, "query": req.query})

    try:
        from ecommerce_brain.observability.setup import investigation_counter
        investigation_counter.add(1, {"intent": "unknown"})
    except Exception:
        pass

    background_tasks.add_task(_run_investigation, query_id, thread_id, initial_state)

    return {"query_id": query_id, "status": "running"}


@router.get("/{query_id}/status")
def poll_status(query_id: str, _: str = Depends(require_api_key)):
    """Poll investigation status. Frontend polls every 2-3s."""
    data = get_status(query_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return data


@router.get("/{query_id}/stream")
async def stream_investigation_status(
    query_id: str,
    _: str = Depends(require_api_key),
):
    """SSE stream — client receives real-time status updates without polling.

    Connect with: EventSource('/api/v1/investigate/{id}/stream')
    Each 'data:' event is a JSON status object identical to the /status response.
    The stream closes automatically when the investigation reaches a terminal state.
    """
    async def event_generator():
        last_data: dict | None = None
        _TERMINAL = {"completed", "blocked", "error", "pending_approval", "interrupted"}
        for _ in range(720):  # 6-minute hard cap (720 × 0.5s)
            current = get_status(query_id)
            if current and current != last_data:
                last_data = current
                yield f"data: {json.dumps(current, default=str)}\n\n"
                if current.get("status") in _TERMINAL:
                    break
            await asyncio.sleep(0.5)
        yield 'data: {"status": "stream_end"}\n\n'

    if get_status(query_id) is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx response buffering
        },
    )


@router.post("/{query_id}/resume")
async def resume_investigation(
    query_id: str,
    decision: HITLDecision,
    _: str = Depends(require_api_key),
):
    """Resume graph after human HITL decision."""
    entry = get_status(query_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if entry.get("status") != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Investigation not awaiting approval (status={entry.get('status')})",
        )

    thread_id = entry["thread_id"]

    try:
        async with get_async_checkpointer() as checkpointer:
            graph = get_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}, "callbacks": []}

            resume_value = {
                "approved": decision.approved,
                "approved_action_ids": decision.approved_action_ids,
                "rejection_reason": decision.rejection_reason,
            }

            from langgraph.types import Command
            resume_command = Command(resume=resume_value)

            async for event in graph.astream(resume_command, config=config):
                node = list(event.keys())[0]
                log.info("graph.resume.event", node=node, query_id=query_id)

            state = await graph.aget_state(config)
            final_state = state.values
            update_status(query_id, {
                "status": "completed",
                "execution_results": final_state.get("execution_results", []),
                "audit_log": final_state.get("audit_log", []),
            })

            return {"query_id": query_id, "status": "completed", "approved": decision.approved}
    except Exception as exc:
        log.error("investigation.resume.failed", query_id=query_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
