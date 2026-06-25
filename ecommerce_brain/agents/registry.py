"""Agent registry — loads YAML definitions at startup, provides tool sets."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

from ecommerce_brain.exceptions import AgentNotFoundError

_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


@dataclass
class AgentSpec:
    """Immutable specification for a domain agent loaded from YAML."""

    name: str
    model: str
    temperature: float
    token_budget: int
    description: str
    system_prompt: str
    whitelisted_tools: list[str] = field(default_factory=list)
    allowed_mcp_servers: list[str] = field(default_factory=list)


@cache
def load_all() -> dict[str, AgentSpec]:
    specs: dict[str, AgentSpec] = {}
    for yaml_file in _DEFINITIONS_DIR.glob("*.yaml"):
        with yaml_file.open() as f:
            data = yaml.safe_load(f)
        spec = AgentSpec(
            name=data["name"],
            model=data.get("model", "gpt-4o"),
            temperature=float(data.get("temperature", 0.15)),
            token_budget=int(data.get("token_budget", 2000)),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            whitelisted_tools=data.get("whitelisted_tools") or [],
            allowed_mcp_servers=data.get("allowed_mcp_servers") or [],
        )
        specs[spec.name] = spec
    return specs


def get_agent(name: str) -> AgentSpec:
    """Return the AgentSpec for the given name.

    Args:
        name: Agent identifier as defined in the YAML file (e.g. "sales_agent").

    Raises:
        AgentNotFoundError: If no spec is registered for ``name``.
    """
    specs = load_all()
    if name not in specs:
        raise AgentNotFoundError(name, available=list(specs))
    return specs[name]
