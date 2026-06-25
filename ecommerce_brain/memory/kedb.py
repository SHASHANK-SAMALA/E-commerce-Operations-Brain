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
from ecommerce_brain.exceptions import DatabaseError, EmbeddingError
from ecommerce_brain.memory.embeddings import embed_text
from ecommerce_brain.schemas.memory import MemoryContext, SimilarIncident

log = structlog.get_logger(__name__)

# Cosine distance threshold for "same pattern" matching (0.0 = identical, 1.0 = orthogonal).
# 0.30 ≈ 70 % semantic similarity — tight enough to avoid merging unrelated issues.
_KEDB_SIMILARITY_THRESHOLD = 0.30


def recall(query: str, top_k: int = 3) -> MemoryContext:
    """Embed query → cosine search KEDB + incidents → MemoryContext.

    Args:
        query: Natural language query to search for similar past incidents.
        top_k: Maximum number of results to return per source.

    Returns:
        MemoryContext populated with KEDB entries and similar incidents.
        Returns an empty MemoryContext when embeddings or DB are unavailable.
    """
    try:
        query_embedding = embed_text(query)
    except EmbeddingError:
        return MemoryContext()

    context = MemoryContext()

    try:
        with get_session() as session:
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
    except Exception as exc:
        log.error("kedb.recall_failed", error=str(exc)[:200])
        return MemoryContext()

    if context.kedb_entries:
        context.historical_pattern_found = True
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
    """Persist a completed investigation to the incident store.

    Args:
        query: Original user query.
        intent: Routing intent (e.g. "diagnose", "action").
        domains: Domain agents that were invoked.
        root_causes: Root cause strings from the synthesis report.
        evidence_score: Reflection evidence quality score.
        actions_proposed: Proposed action dicts from the synthesis node.
        actions_approved: Approved action dicts from the HITL node.
        actions_executed: Execution result dicts from the action executor.
        tokens_used: Total LLM tokens consumed.
        duration_ms: Wall-clock investigation duration in milliseconds.

    Returns:
        String representation of the new incident's primary key.

    Raises:
        DatabaseError: If the DB write fails.
    """
    try:
        embedding = embed_text(query)
    except EmbeddingError:
        embedding = None

    try:
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
            incident_id = str(incident.id)
    except Exception as exc:
        log.error("kedb.save_incident_failed", error=str(exc)[:200])
        raise DatabaseError(str(exc)) from exc
    else:
        return incident_id


def save_or_update_kedb_entry(
    query: str,
    root_causes: list[str],
    resolution_steps: list[str],
    affected_domains: list[str],
) -> str | None:
    """Upsert a KEDB entry from a completed investigation.

    If a semantically similar entry already exists (cosine distance < threshold),
    increment its occurrence count and merge any new resolution steps.
    Otherwise create a fresh entry.

    Args:
        query: Original user query (used as the symptom summary and for embedding).
        root_causes: Root cause strings to record.
        resolution_steps: Actions taken, to merge into the KEDB entry.
        affected_domains: Domain agents that were relevant.

    Returns:
        KEDB entry ID string, or None if root_causes is empty or embedding fails.

    Raises:
        DatabaseError: If the DB write fails.
    """
    if not root_causes:
        return None

    try:
        embedding = embed_text(query)
    except EmbeddingError:
        return None

    try:
        with get_session() as session:
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
    except Exception as exc:
        log.error("kedb.write_failed", error=str(exc)[:200])
        raise DatabaseError(str(exc)) from exc
    else:
        return entry_id
