# AI E-Commerce Operations Brain

An autonomous multi-agent AI system that answers operational questions across sales, inventory, marketing, and customer support — in natural language, in under 15 seconds, with human approval before any action is executed.

---

## Table of Contents

1. [What](#what)
2. [Why](#why)
3. [How](#how)
4. [Architecture at a Glance](#architecture-at-a-glance)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Local Setup](#local-setup)
8. [Configuration](#configuration)
9. [Running the System](#running-the-system)
10. [Usage](#usage)
11. [API Reference](#api-reference)
12. [Running Tests](#running-tests)
13. [Observability](#observability)
14. [Design Document](#design-document)

---

## What

The E-Commerce Operations Brain is a production-grade agentic AI system. A business user asks a question in plain English — from a web UI or via voice — and the system:

- Identifies what kind of question it is (diagnosis, action, historical recall, or a report)
- Pulls live data from up to four business domains simultaneously
- Scores the quality of evidence it has collected
- Generates a structured root-cause report with specific, actionable recommendations
- For action-intent queries: pauses and waits for explicit human approval before executing anything
- Persists every resolved investigation to a searchable memory, so future similar incidents surface historical context automatically

**Supported query types:**

| Query | What happens |
|---|---|
| `"Why did revenue drop 18% yesterday?"` | Diagnose — all four domain agents run in parallel |
| `"Which products are critically low on stock?"` | Diagnose — inventory agent only |
| `"Restock SKU-001 and resume CAM-044"` | Action — HITL gate, human approves before anything runs |
| `"What did we do last time this happened?"` | Memory recall — answered directly from KEDB/Mem0, zero LLM cost |
| `"Give me a full business health summary"` | Report — all four domains, no action gate |

---

## Why

### The Problem

An e-commerce analyst observing a sudden revenue drop faces four fragmented data sources: a sales dashboard, an inventory system, a marketing platform, and a customer support queue. Correlating them to a root cause requires manually querying each, cross-referencing the findings, forming a hypothesis, and deciding on an action. This typically takes 1–3 hours, is inconsistent across analysts, and is unavailable outside business hours.

### The Approach

Rather than building another dashboard, this system gives the data a voice. Domain-specialist agents run in parallel, each with access to its own data server. A synthesis model merges their findings. A deterministic reflection node scores evidence quality and can re-dispatch agents if coverage is weak. Every resolved incident feeds back into a memory layer that makes the next similar investigation faster and more accurate.

### Why These Specific Design Choices

| Decision | Reasoning |
|---|---|
| LangGraph for orchestration | Native `interrupt()` for HITL, `Send()` for parallel fan-out, `PostgresSaver` for state persistence across restarts. No other framework supports all three. |
| MCP for tool access | Domain agents never call Python functions directly. Tools are isolated services — swapping a mock data server for a live one requires no code change. |
| Deterministic routing first, LLM second | A rules engine handles 95% of queries in under 1 ms with zero token cost. The LLM is only called when the rules engine's confidence is low. |
| Deterministic reflection | `evidence_score` is a measurable fraction of data coverage, not a model's confidence estimate. This makes it auditable and reproducible. |
| HITL always required for actions | The system never executes a state-changing action without explicit human approval. Dry-run results are shown before approval so the human sees exactly what will happen. |
| `memory_answer` node for history queries | Queries about past incidents are answered entirely from the KEDB/Mem0 memory without calling any domain agent or LLM, making them fast and free. |

---

## How

### Request Lifecycle (simplified)

```
User submits query
    ↓
FastAPI: API key check → rate limit → injection check → 202 Accepted
    ↓ (background task)
guardrail node: length check + injection check (second pass)
    ↓
coordinator node: rules engine classifies intent + domains
    ↓
memory_recall node: KEDB cosine search + Mem0 recall
    ↓
    ├── intent = memory_query → memory_answer node → memory_writer → DONE
    │
    └── other intents → domain agents run in parallel
                            ↓
                        reflection node: compute evidence_score
                            ↓
                    evidence low AND loops < 2 → back to coordinator
                    evidence OK → synthesis node (gpt-4o)
                            ↓
                        hitl node
                            ├── diagnostic → memory_writer → DONE
                            └── action intent → interrupt() → wait for POST /resume
                                    ↓ (after approval)
                                action_executor → memory_writer → DONE
```

### Parallelism

Two levels of parallelism ensure the total investigation time is bounded by the **slowest single agent**, not the sum of all agents:

- **Level 1:** Only the required domain agents are dispatched. A stockout query spawns only the inventory agent.
- **Level 2:** Inside each agent, all MCP tools are called concurrently. A 5-tool agent has the same latency as a 1-tool agent.

---

## Architecture at a Glance

```
User (browser or voice)
        │
        ▼
FastAPI Gateway  ── API key · rate limit · injection check
        │
        ▼
  LangGraph State Machine
  ┌─────────────────────────────────────────────────────┐
  │  guardrail → coordinator → memory_recall            │
  │                                ├── memory_answer    │
  │                                └── [parallel]       │
  │                                    sales_agent      │
  │                                    inventory_agent  │
  │                                    marketing_agent  │
  │                                    support_agent    │
  │                                        │            │
  │                                   reflection        │
  │                                        │            │
  │                                   synthesis         │
  │                                        │            │
  │                                      hitl ── ⏸ pause│
  │                                        │            │
  │                               action_executor       │
  │                                        │            │
  │                                  memory_writer      │
  └─────────────────────────────────────────────────────┘
        │
        ▼
PostgreSQL + pgvector    Redis (status)    Mem0 (session memory)
        │
        ▼
MCP Servers (×5)         Azure OpenAI       Prometheus + Tempo
```

For the full architectural diagrams, schema contracts, and node-by-node specifications, see [HLD_LLD.md](HLD_LLD.md).

---

## Project Structure

```
project-4/
├── HLD_LLD.md                       ← Architecture design document (HLD + LLD)
├── README.md                        ← This file
├── pyproject.toml                   ← Pinned dependencies (uv / pip)
├── docker-compose.yml               ← Full stack: Postgres, Redis, backend, MCP servers
├── run_uvicorn.py                   ← Local dev server launcher (no Docker)
├── start_mcp_servers.py             ← Starts all 5 MCP servers locally
│
├── ecommerce_brain/
│   ├── api/
│   │   ├── main.py                  ← FastAPI app entry point
│   │   ├── deps.py                  ← API key dependency
│   │   ├── status_store.py          ← Redis-backed investigation status
│   │   └── routers/
│   │       ├── investigate.py       ← Start / status / resume / stream
│   │       ├── audio.py             ← Whisper transcription
│   │       └── export.py            ← CSV export
│   │
│   ├── graph/
│   │   ├── graph.py                 ← StateGraph assembly + PostgresSaver
│   │   ├── state.py                 ← GraphState TypedDict
│   │   ├── nodes/
│   │   │   ├── guardrail.py         ← Injection + length check
│   │   │   ├── coordinator.py       ← Rules routing + LLM fallback
│   │   │   ├── memory_recall.py     ← KEDB + Mem0 recall
│   │   │   ├── memory_answer.py     ← Handles memory_query without domain agents
│   │   │   ├── domain_agents.py     ← Sales / inventory / marketing / support
│   │   │   ├── reflection.py        ← Deterministic evidence_score
│   │   │   ├── synthesis.py         ← RootCauseReport + ProposedActions
│   │   │   ├── hitl.py              ← Dry-run + interrupt()
│   │   │   ├── action_executor.py   ← MCP dispatch post-HITL
│   │   │   └── memory_writer.py     ← Incident persistence
│   │   └── routing/
│   │       └── rules_engine.py      ← Ordered regex routing rules
│   │
│   ├── agents/
│   │   ├── react_agent.py           ← ReAct agent graph factory
│   │   ├── registry.py              ← YAML loader (cached singleton)
│   │   └── definitions/             ← One YAML per agent
│   │
│   ├── mcp_servers/                 ← Five FastMCP servers (ports 8001–8005)
│   ├── tools/                       ← Tool registry + MCP loader
│   ├── memory/                      ← KEDB, KADB, Mem0 integration
│   ├── schemas/                     ← Pydantic models (inputs, outputs, routing, memory)
│   ├── db/                          ← SQLAlchemy engine, ORM models, seed script
│   ├── guardrails/                  ← 16-pattern injection detector
│   ├── observability/               ← structlog + OpenTelemetry + LangSmith setup
│   ├── config/
│   │   └── settings.py              ← pydantic-settings (all config from .env)
│   └── llm.py                       ← LLM factory functions + embedding singleton
│
├── evaluation/                      ← DeepEval test suite + metrics
├── frontend/                        ← React/Vite SPA
├── tests/                           ← Unit + integration tests
├── scripts/                         ← Utility scripts (port check, kill, reset)
└── docker/                          ← Dockerfiles + Nginx + Prometheus config
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Tested on 3.11 and 3.12 |
| PostgreSQL | 16 + pgvector extension | Provided via Docker Compose |
| Redis | 7+ | Provided via Docker Compose |
| Azure OpenAI | — | gpt-4o deployment + text-embedding-3-small deployment required |
| Node.js | 18+ | Frontend only |
| Docker + Docker Compose | v2+ | Optional; required only for the full containerised stack |

---

## Local Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd project-4

# Using uv (recommended)
uv sync --extra dev

# Or using pip
pip install -e ".[dev]"
```

### 2. Copy and fill the environment file

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

```env
# Azure OpenAI (required)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_MODEL=gpt-4o
AZURE_OPENAI_EMBEDDING_MODEL=text-embedding-3-small-1

# API security
API_KEY=your-api-key-for-this-service

# Database (Docker Compose provides these defaults)
DATABASE_URL=postgresql://ecommerce:ecommerce@localhost:5432/ecommerce_brain
REDIS_URL=redis://localhost:6379/0
```

### 3. Start infrastructure

```bash
# Start PostgreSQL and Redis only (for local dev without full Docker stack)
docker compose up postgres redis -d

# Or start the entire stack including all services
docker compose up -d
```

### 4. Initialise the database and seed demo data

```bash
python -m ecommerce_brain.db.seed
```

### 5. Start MCP servers

```bash
python start_mcp_servers.py
```

This starts five FastMCP servers on ports 8001–8005. You can verify they are reachable:

```bash
python scripts/check_mcp_ports.py
```

### 6. Start the backend API

```bash
python run_uvicorn.py
# or
uvicorn ecommerce_brain.api.main:app --reload --host 127.0.0.1 --port 8000
```

### 7. Start the frontend (optional)

```bash
cd frontend
npm install
npm run dev
# Opens on http://localhost:3000
```

---

## Configuration

All configuration is loaded from `.env` via `pydantic-settings`. No values are hardcoded.

### Required

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint URL |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_MODEL` | Deployment name for gpt-4o (used for agents and synthesis) |
| `AZURE_OPENAI_EMBEDDING_MODEL` | Deployment name for text-embedding-3-small |
| `API_KEY` | Key that all API clients must send in the `X-API-Key` header |

### Optional (with defaults)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://ecommerce:ecommerce@localhost:5432/ecommerce_brain` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `OTEL_ENABLED` | `true` | Enable OpenTelemetry tracing and metrics |
| `OTEL_ENDPOINT` | `http://tempo:4317` | OTLP gRPC collector endpoint |
| `LLM_REQUEST_TIMEOUT` | `90` | LLM call timeout in seconds |
| `MAX_TOKENS_PER_INVESTIGATION` | `12000` | Token budget per investigation |
| `MCP_SALES_URL` | `http://localhost:8001/sse` | Override for Docker networking |
| `MCP_INVENTORY_URL` | `http://localhost:8002/sse` | Override for Docker networking |
| `MCP_MARKETING_URL` | `http://localhost:8003/sse` | Override for Docker networking |
| `MCP_SUPPORT_URL` | `http://localhost:8004/sse` | Override for Docker networking |
| `MCP_ACTION_URL` | `http://localhost:8005/sse` | Override for Docker networking |
| `LANGCHAIN_TRACING_V2` | `false` | Enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | LangSmith API key |
| `USE_LOCAL_ROUTING_LLM` | `false` | Use Ollama/Mistral for routing fallback |

---

## Running the System

### Docker Compose (recommended for demo / staging)

```bash
docker compose up -d
```

This brings up: PostgreSQL, Redis, the FastAPI backend, all five MCP servers, the React frontend (served via Nginx), Prometheus, Grafana, and Tempo.

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

### Local development (no Docker)

```bash
# Terminal 1 — Infrastructure
docker compose up postgres redis -d

# Terminal 2 — MCP servers
python start_mcp_servers.py

# Terminal 3 — Backend API
python run_uvicorn.py

# Terminal 4 — Frontend
cd frontend && npm run dev
```

---

## Usage

### Submit a query via API

```bash
curl -X POST http://localhost:8000/api/v1/investigate \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "Why did revenue drop significantly this week?"}'
```

Response:
```json
{ "query_id": "inv-abc123def456", "status": "running" }
```

### Poll for results

```bash
curl http://localhost:8000/api/v1/investigate/inv-abc123def456/status \
  -H "X-API-Key: your-api-key"
```

### Approve a HITL action

When status is `pending_approval`:

```bash
curl -X POST http://localhost:8000/api/v1/investigate/inv-abc123def456/resume \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "approved_action_ids": ["act-xyz789"],
    "rejection_reason": null
  }'
```

### Example queries to try

| Query | Expected behaviour |
|---|---|
| `"Why has revenue dropped this week?"` | Multi-domain diagnosis, all 4 agents |
| `"Which SKUs need immediate restocking?"` | Inventory-only diagnosis |
| `"What is the status of our ad campaigns?"` | Marketing-only diagnosis |
| `"Restock ELEC-001 with 500 units"` | Action intent → HITL gate triggered |
| `"What did we do last time sales dropped?"` | Memory recall → no agents spawned |
| `"Give me a full business health report"` | Report intent, all 4 domains |

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/investigate` | Yes | Start a new investigation |
| `GET` | `/api/v1/investigate/{id}/status` | Yes | Get current status and results |
| `POST` | `/api/v1/investigate/{id}/resume` | Yes | Submit HITL approval or rejection |
| `POST` | `/api/v1/audio/transcribe` | Yes | Transcribe audio to text (Azure Whisper) |
| `GET` | `/api/v1/export/incidents` | Yes | Export incident history as CSV |
| `GET` | `/health` | No | Health check |
| `GET` | `/docs` | No | Interactive OpenAPI documentation |

Full request/response schemas are documented in [HLD_LLD.md — Section 13](HLD_LLD.md) and in the interactive Swagger UI at `/docs`.

---

## Running Tests

### Unit and integration tests

```bash
pytest tests/ -v
```

### Evaluation suite (requires running system)

```bash
# Routing-only evaluation (no API calls needed)
pytest evaluation/ -v -k "routing"

# Full agent evaluation (requires Azure OpenAI + running MCP servers)
deepeval test run evaluation/test_agents.py
```

### End-to-end tests (requires full running stack)

```bash
python scripts/e2e_tests.py
```

The E2E suite covers: auth checks, injection blocking, off-topic guardrail, sales diagnosis, marketing HITL approval flow, support spike, inventory restock, memory recall, and HITL rejection.

---

## Observability

### Structured logs

All logs are emitted as JSON via `structlog`. Every log event is tagged with `query_id`, making it easy to trace a full investigation across node transitions:

```bash
docker compose logs backend --follow | python -m json.tool
```

### LangSmith (LLM traces)

Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY=...` in `.env`. Every investigation's LLM calls — including prompts, responses, and token counts — appear in the LangSmith dashboard.

### Prometheus + Grafana

Available at http://localhost:3001 when running via Docker Compose. Metrics include:
- HTTP request rate and latency
- LLM call latency per node (`synthesis`, `coordinator`, `domain agents`)
- Investigation completion counts

### OpenTelemetry traces

Traces are exported to Tempo (OTLP gRPC on port 4317) and viewable in Grafana via the Tempo datasource. Set `OTEL_ENABLED=false` in `.env` to disable when running tests or in CI.

---

## Design Document

For the full architecture including:
- High-Level Design with component diagrams
- LangGraph state machine diagram
- Node-by-node technical specifications
- Database schema (ER diagram)
- Pydantic schema contracts
- HITL sequence diagram
- Memory architecture
- Evidence score formula
- MCP server isolation rationale

See **[HLD_LLD.md](HLD_LLD.md)**.

---

## Resetting State

```bash
# Reset Mem0 memory store
python scripts/reset_mem0.py

# Kill all MCP server ports before restart
python scripts/kill_mcp_ports.py

# Drop and recreate the database
docker compose down -v && docker compose up postgres -d
python -m ecommerce_brain.db.seed
```

---

## Key Constraints and Assumptions

- **Mock data only.** All five MCP servers return realistic but synthetic data. Connecting to real data sources requires replacing the MCP server implementations — the agent code requires no changes.
- **Azure OpenAI required.** The system uses Azure-hosted gpt-4o and text-embedding-3-small. AWS Bedrock or direct OpenAI endpoints would require changing the LLM factory in `llm.py`.
- **Single-tenant design.** The current implementation assumes one organisation. Multi-tenant isolation would require per-tenant database schemas and API key namespacing.
- **Polling model.** The frontend polls `/status` every 2–3 seconds. The architecture supports SSE streaming (stub exists) but polling was chosen for simplicity.
