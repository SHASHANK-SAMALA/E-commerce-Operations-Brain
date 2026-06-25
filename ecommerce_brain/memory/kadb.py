"""KADB — Known Action Database.

Tracks historical action success rates for evidence-based recommendations.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import KADBEntry

log = structlog.get_logger(__name__)


def get_action_stats(action_type: str) -> dict:
    """Return success rate and average revenue impact for an action type.

    Args:
        action_type: Tool function name (e.g. "restock_product").

    Returns:
        Dict with keys: action_type, success_rate (float | None),
        total_executions (int), avg_revenue_impact (float).
    """
    with get_session() as session:
        entry = session.scalar(
            select(KADBEntry).where(KADBEntry.action_type == action_type)
        )
        if not entry:
            return {
                "action_type": action_type,
                "success_rate": None,
                "total_executions": 0,
                "avg_revenue_impact": 0.0,
            }
        return {
            "action_type": action_type,
            "success_rate": round(entry.success_rate, 2),
            "total_executions": entry.total_executions,
            "avg_revenue_impact": entry.avg_revenue_impact,
        }


def record_execution(action_type: str, success: bool, revenue_impact: float = 0.0) -> None:
    """Increment execution counters after an action completes.

    Uses an incremental running average so the full history need not be
    retained — the single KADB row is updated in place.

    Args:
        action_type: Tool function name that was executed.
        success: Whether the execution succeeded.
        revenue_impact: Estimated revenue change attributed to this action.
    """
    try:
        with get_session() as session:
            entry = session.scalar(
                select(KADBEntry).where(KADBEntry.action_type == action_type)
            )
            if not entry:
                entry = KADBEntry(
                    action_type=action_type,
                    total_executions=0,
                    successful_executions=0,
                )
                session.add(entry)
            entry.total_executions += 1
            if success:
                entry.successful_executions += 1
            n = entry.total_executions
            entry.avg_revenue_impact = ((entry.avg_revenue_impact * (n - 1)) + revenue_impact) / n
    except Exception as exc:
        log.error("kadb.record_failed", action_type=action_type, error=str(exc))
