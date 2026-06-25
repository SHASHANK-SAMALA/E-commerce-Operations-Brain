"""Memory-layer schemas shared between kedb.py and graph state.

Using Pydantic BaseModel (rather than dataclass) gives automatic validation,
serialisation, and consistency with all other schemas in this package.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimilarIncident(BaseModel):
    """A past incident retrieved from the vector store during memory recall."""

    id: str
    query: str
    root_causes: list[str]
    resolution_steps: list[str]
    evidence_score: float
    created_at: str


class MemoryContext(BaseModel):
    """Aggregated memory context passed into the graph for a single investigation."""

    similar_incidents: list[SimilarIncident] = Field(default_factory=list)
    kedb_entries: list[dict] = Field(default_factory=list)
    historical_pattern_found: bool = False
    recommended_actions_from_history: list[str] = Field(default_factory=list)
    # Domain-scoped mem0 recalls — keyed by domain name ("sales", "inventory", etc.).
    # Populated in memory_recall_node; consumed by _get_domain_memory_hint so that
    # inventory patterns never bleed into the sales or marketing agent context.
    domain_memories: dict[str, list[str]] = Field(default_factory=dict)
