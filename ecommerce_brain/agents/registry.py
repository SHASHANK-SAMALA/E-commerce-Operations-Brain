"""Agent registry — loads YAML definitions at startup, provides tool sets."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml
from langchain_core.tools import BaseTool

from ecommerce_brain.tools.registry import registry as tool_registry

_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


@dataclass
class AgentSpec:
    name: str
    model: str
    temperature: float
    token_budget: int
    description: str
    system_prompt: str
    whitelisted_tools: list[str] = field(default_factory=list)
    allowed_mcp_servers: list[str] = field(default_factory=list)

    def get_tools(self) -> list[BaseTool]:
        """Return only the tools this agent is allowed to call."""
        missing = [t for t in self.whitelisted_tools if t not in tool_registry]
        if missing:
            raise KeyError(f"Agent '{self.name}' references unknown tools: {missing}")
        return [tool_registry[t] for t in self.whitelisted_tools]


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
    specs = load_all()
    if name not in specs:
        raise KeyError(f"Agent '{name}' not found in registry. Available: {list(specs)}")
    return specs[name]
