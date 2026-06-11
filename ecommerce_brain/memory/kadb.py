"""KADB — Known Action Database.

Tracks historical action success rates for evidence-based recommendations.
"""

from __future__ import annotations

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import KADBEntry


def get_action_stats(action_type: str) -> dict:
    """Return success rate + avg revenue impact for a given action type."""
    with get_session() as session:
        entry = session.query(KADBEntry).filter(KADBEntry.action_type == action_type).first()
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
    """Increment execution counters after an action completes."""
    with get_session() as session:
        entry = session.query(KADBEntry).filter(KADBEntry.action_type == action_type).first()
        if not entry:
            entry = KADBEntry(action_type=action_type, total_executions=0, successful_executions=0)
            session.add(entry)
        entry.total_executions += 1
        if success:
            entry.successful_executions += 1
        # Incremental average
        n = entry.total_executions
        entry.avg_revenue_impact = ((entry.avg_revenue_impact * (n - 1)) + revenue_impact) / n
