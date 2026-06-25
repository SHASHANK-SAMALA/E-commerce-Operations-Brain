"""CSV export router — export investigation results and incident history."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ecommerce_brain.api.deps import require_api_key
from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import Incident

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/incidents")
def export_incidents(
    limit: int = Query(default=500, ge=1, le=5000, description="Max rows to export"),
    _: str = Depends(require_api_key),
):
    """Export incident history as CSV.

    Args:
        limit: Maximum number of rows to return (1–5000, default 500).
    """
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id", "query", "intent", "domains_investigated", "root_causes",
            "evidence_score", "tokens_used", "duration_ms", "created_at",
        ],
    )
    writer.writeheader()
    with get_session() as session:
        incidents = session.scalars(
            select(Incident).order_by(Incident.created_at.desc()).limit(limit)
        ).all()
        for inc in incidents:
            writer.writerow({
                "id": str(inc.id),
                "query": inc.query,
                "intent": inc.intent,
                "domains_investigated": "|".join(inc.domains_investigated or []),
                "root_causes": " | ".join(inc.root_causes or []),
                "evidence_score": inc.evidence_score,
                "tokens_used": inc.tokens_used,
                "duration_ms": inc.duration_ms,
                "created_at": str(inc.created_at),
            })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=incidents.csv"},
    )
