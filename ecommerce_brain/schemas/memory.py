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
