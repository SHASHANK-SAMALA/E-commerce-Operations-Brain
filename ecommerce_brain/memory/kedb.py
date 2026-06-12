"""KEDB — Known Error Database.

Semantic search over past incidents using pgvector.
Returns MemoryContext to pre-inform domain agents before investigation.
Also writes new KEDB entries from completed investigations.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import Incident, KEDBEntry
from ecommerce_brain.llm import embedding_client
from ecommerce_brain.schemas.memory import MemoryContext, SimilarIncident

log = structlog.get_logger(__name__)

# Re-export so existing `from ecommerce_brain.memory.kedb import MemoryContext` still works.
__all__ = [
    "MemoryContext",
    "SimilarIncident",
    "recall",
    "save_incident",
    "save_or_update_kedb_entry",
]

# Cosine distance threshold for "same pattern" matching (0.0 = identical, 1.0 = orthogonal).
# 0.30 ≈ 70 % semantic similarity — tight enough to avoid merging unrelated issues.
_KEDB_SIMILARITY_THRESHOLD = 0.30


def recall(query: str, top_k: int = 3) -> MemoryContext:
    """Embed query → cosine search KEDB + incidents → MemoryContext."""
    client = embedding_client()
    query_embedding = client.embed_query(query)

    context = MemoryContext()

    with get_session() as session:
        # Search KEDB entries
        kedb_hits = KEDBEntry.search_similar(session, query_embedding, top_k=top_k)
        for entry in kedb_hits:
            context.kedb_entries.append({
                "id": str(entry.id),
                "symptom_summary": entry.symptom_summary,
                "root_cause": entry.root_cause,
                "resolution_steps": entry.resolution_steps,
                "affected_domains": entry.affected_domains,
                "occurrence_count": entry.occurrence_count,
            })

        # Search past resolved incidents
        past = Incident.search_similar(session, query_embedding, top_k=top_k)
        for inc in past:
            context.similar_incidents.append(
                SimilarIncident(
                    id=str(inc.id),
                    query=inc.query,
                    root_causes=inc.root_causes,
                    resolution_steps=[],
                    evidence_score=inc.evidence_score,
                    created_at=str(inc.created_at),
                )
            )

    if context.kedb_entries:
        context.historical_pattern_found = True
        # Surface first resolution steps as recommended actions
        for entry in context.kedb_entries[:1]:
            context.recommended_actions_from_history.extend(entry.get("resolution_steps", []))

    return context


def save_incident(
    query: str,
    intent: str,
    domains: list[str],
    root_causes: list[str],
    evidence_score: float,
    actions_proposed: list[dict],
    actions_approved: list[dict],
    actions_executed: list[dict],
    tokens_used: int,
    duration_ms: int,
) -> str:
    """Persist a completed investigation to the incident store."""
    client = embedding_client()
    embedding = client.embed_query(query)

    with get_session() as session:
        incident = Incident(
            query=query,
            intent=intent,
            domains_investigated=domains,
            root_causes=root_causes,
            evidence_score=evidence_score,
            actions_proposed=actions_proposed,
            actions_approved=actions_approved,
            actions_executed=actions_executed,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            embedding=embedding,
        )
        session.add(incident)
        session.flush()
        return str(incident.id)


def save_or_update_kedb_entry(
    query: str,
    root_causes: list[str],
    resolution_steps: list[str],
    affected_domains: list[str],
) -> str | None:
    """Upsert a KEDB entry from a completed investigation.

    If a semantically similar entry already exists (cosine distance < threshold),
    increment its occurrence count and merge any new resolution steps.
    Otherwise create a fresh entry. Returns the KEDB entry ID or None on error.
    """
    if not root_causes:
        return None

    client = embedding_client()
    embedding = client.embed_query(query)

    try:
        with get_session() as session:
            # Find the nearest existing KEDB entry within the similarity threshold.
            stmt = (
                select(KEDBEntry)
                .where(KEDBEntry.embedding.isnot(None))
                .where(KEDBEntry.embedding.cosine_distance(embedding) < _KEDB_SIMILARITY_THRESHOLD)
                .order_by(KEDBEntry.embedding.cosine_distance(embedding))
                .limit(1)
            )
            existing = session.scalars(stmt).first()

            if existing:
                existing.occurrence_count += 1
                existing.last_seen = datetime.now(tz=UTC)
                # Merge resolution steps that aren't already recorded.
                known_steps: set[str] = set(existing.resolution_steps or [])
                merged = list(existing.resolution_steps or [])
                for step in resolution_steps:
                    if step not in known_steps:
                        merged.append(step)
                        known_steps.add(step)
                existing.resolution_steps = merged
                entry_id = str(existing.id)
                log.info("kedb.updated", entry_id=entry_id, occurrences=existing.occurrence_count)
            else:
                new_entry = KEDBEntry(
                    symptom_summary=query,
                    root_cause="; ".join(root_causes),
                    resolution_steps=resolution_steps,
                    affected_domains=affected_domains,
                    occurrence_count=1,
                    embedding=embedding,
                )
                session.add(new_entry)
                session.flush()
                entry_id = str(new_entry.id)
                log.info("kedb.created", entry_id=entry_id)

            return entry_id
    except Exception as exc:
        log.error("kedb.write_failed", error=str(exc)[:200])
        return None
