"""Memory-layer schemas shared between kedb.py and graph state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SimilarIncident:
    id: str
    query: str
    root_causes: list[str]
    resolution_steps: list[str]
    evidence_score: float
    created_at: str


@dataclass
class MemoryContext:
    similar_incidents: list[SimilarIncident] = field(default_factory=list)
    kedb_entries: list[dict] = field(default_factory=list)
    historical_pattern_found: bool = False
    recommended_actions_from_history: list[str] = field(default_factory=list)
    # Domain-scoped mem0 recalls — keyed by domain name ("sales", "inventory", etc.).
    # Populated in memory_recall_node; consumed by _get_domain_memory_hint so that
    # inventory patterns never bleed into the sales or marketing agent context.
    domain_memories: dict[str, list[str]] = field(default_factory=dict)
