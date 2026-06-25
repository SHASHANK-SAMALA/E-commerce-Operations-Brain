"""Synthesis node — Coordinator LLM merges all domain reports → RootCauseReport."""

from __future__ import annotations

import json
import time

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry import trace

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.llm import synthesis_llm
from ecommerce_brain.memory.kadb import get_action_stats
from ecommerce_brain.observability.safe_metrics import safe_record
from ecommerce_brain.observability.setup import llm_latency_histogram
from ecommerce_brain.schemas.outputs import ProposedAction, RootCauseReport

log = structlog.get_logger(__name__)
_tracer = trace.get_tracer("ecommerce_brain.synthesis")

_MAX_ACTIONS = 4

# Channel names that LLMs frequently confuse with campaign_id values.
# Actions using these as campaign_id are blocked in post-processing.
_CHANNEL_NAMES: frozenset[str] = frozenset({
    "google", "meta", "email", "tiktok",
    "instagram", "facebook", "youtube", "bing",
})

_SYSTEM = """You are a senior e-commerce operations analyst.
You receive domain reports from Sales, Inventory, Marketing, and Support agents.
Synthesize them into a detailed RootCauseReport JSON. Be specific and use exact numbers.

CRITICAL — DATA INTEGRITY RULES:
- Base ALL proposed_actions exclusively on the CURRENT domain reports provided below.
- Historical KEDB context is for pattern recognition ONLY — never propose actions for
  SKUs, campaigns, or categories that do not appear in the current domain reports.
- If a report field is empty (e.g., stockouts=[], paused_campaigns=[]), that domain has
  NO actionable issues. Do NOT invent actions for it.

EXACT TOOL SIGNATURES — parameters MUST match these exactly or the executor will reject them:

  restock_product
    params: {"sku": "<string>", "quantity": <integer 1-10000>}
    → ONLY when InventoryReport.stockouts OR near_stockout_skus is NON-EMPTY.
    → Use ONE sku per action — ONE action per SKU, not a bulk list.
    → Max 3 restock actions total. Use exact SKU codes from the inventory report.

  resume_campaign
    params: {"campaign_id": "<string>"}
    → ONLY when MarketingReport.paused_campaigns is NON-EMPTY.
    → Use exact campaign_id values from paused_campaigns list.

  increase_campaign_budget
    params: {"campaign_id": "<string>", "increase_pct": <float 1.0-200.0>}
    → ONLY when MarketingReport.roas_delta_pct < -10 OR underperforming_channels NON-EMPTY.
    → campaign_id MUST be the exact `campaign_id` field from the data (e.g. "CAM-001").
      NEVER use the channel name ("google", "meta", "tiktok") as the campaign_id.
    → increase_pct is a PERCENTAGE value e.g. 20.0 means +20%. NOT an absolute dollar amount.

  apply_discount_promotion
    params: {"category": "<single category string>", "discount_pct": <float 1.0-50.0>}
    → ONLY when SalesReport.revenue_delta_pct < -5 AND top_declining_categories NON-EMPTY.
    → category MUST be ONE plain string — never a list, never a dict.

RULES for proposed_actions:
- action_type MUST EXACTLY match one of the four names above (case-sensitive).
- Propose at most 5 actions total. Fewer high-confidence actions beats many uncertain ones.
- Prefer diverse action types (one per domain) over multiple actions of the same type.
- If intent is NOT "action", proposed_actions MUST be an empty list.
- If the query is purely diagnostic with no clear operational lever, omit proposed_actions.

NEGATIVE EXAMPLES — these are the most common LLM mistakes, all will be REJECTED:
  ✗ {{"action_type": "restock_product", "params": {{"skus": ["ELEC-001", "ELEC-004"]}}}}  ← bulk list
  ✓ ONE action per SKU: {{"action_type": "restock_product", "params": {{"sku": "ELEC-001", "quantity": 500}}}}

  ✗ {{"action_type": "increase_campaign_budget", "params": {{"campaign_id": "google"}}}}  ← channel name
  ✓ Use exact campaign_id from data: {{"action_type": "increase_campaign_budget", "params": {{"campaign_id": "CAM-003", "increase_pct": 20.0}}}}

  ✗ {{"action_type": "apply_discount_promotion", "params": {{"category": ["Electronics", "Sports"]}}}}  ← list
  ✓ ONE action per category: {{"action_type": "apply_discount_promotion", "params": {{"category": "Electronics", "discount_pct": 10.0}}}}

For root_causes: include exact metrics, domain, evidence, and confidence level.
The summary field must be 2-4 sentences covering all key findings with numbers.
Return only the RootCauseReport JSON — no prose.
"""


def _intent_allows_actions(intent: str | None) -> bool:
    """Return True only for explicit action intent — diagnose/report/memory_query are read-only."""
    return intent == "action"


def _build_kadb_context() -> str:
    """Surface historical action success rates to guide the LLM's recommendations."""
    action_types = [
        "restock_product",
        "resume_campaign",
        "increase_campaign_budget",
        "apply_discount_promotion",
    ]
    lines: list[str] = []
    for at in action_types:
        stats = get_action_stats(at)
        if stats["total_executions"] > 0:
            lines.append(
                f"  {at}: {stats['total_executions']} past executions, "
                f"{(stats['success_rate'] or 0) * 100:.0f}% success rate, "
                f"avg revenue impact ${stats['avg_revenue_impact']:.0f}"
            )
    if not lines:
        return ""
    return (
        "\n\n=== ACTION SUCCESS HISTORY "
        "(use to set historical_success_rate on proposed actions) ===\n"
        + "\n".join(lines)
        + "\n=== END ACTION HISTORY ==="
    )


def _filter_actions(
    proposed: list[ProposedAction],
    inventory_report,
    marketing_report,
    sales_report,
) -> list[ProposedAction]:
    """Post-processing guard: drop LLM-generated actions that violate data integrity rules.

    This runs in code so violations are impossible to prompt-engineer around.
    """
    valid_skus: set[str] = set()
    if inventory_report is not None:
        for item in getattr(inventory_report, "stockouts", []):
            valid_skus.add(getattr(item, "sku", ""))
        valid_skus.update(getattr(inventory_report, "near_stockout_skus", []))

    paused_campaign_ids: set[str] = set()
    if marketing_report is not None:
        for c in getattr(marketing_report, "paused_campaigns", []):
            paused_campaign_ids.add(getattr(c, "campaign_id", ""))

    clean: list[ProposedAction] = []
    for action in proposed:
        atype = action.action_type
        params = action.parameters

        if atype == "restock_product":
            sku = params.get("sku", "")
            if not valid_skus:
                log.warning("synthesis.action_blocked", action_type=atype, reason="no_stockouts_in_report")
                continue
            if sku not in valid_skus:
                log.warning("synthesis.action_blocked", action_type=atype, sku=sku, reason="sku_not_in_report")
                continue

        elif atype == "increase_campaign_budget":
            cid = params.get("campaign_id", "")
            if cid.lower() in _CHANNEL_NAMES:
                log.warning("synthesis.action_blocked", action_type=atype, reason="channel_name_as_id", value=cid)
                continue
            if marketing_report is not None:
                roas_delta = getattr(marketing_report, "roas_delta_pct", 0.0)
                underperforming = getattr(marketing_report, "underperforming_channels", [])
                if roas_delta >= -10.0 and not underperforming:
                    log.warning("synthesis.action_blocked", action_type=atype, reason="roas_acceptable")
                    continue

        elif atype == "resume_campaign":
            if not paused_campaign_ids:
                log.warning("synthesis.action_blocked", action_type=atype, reason="no_paused_campaigns")
                continue
            if params.get("campaign_id") not in paused_campaign_ids:
                log.warning("synthesis.action_blocked", action_type=atype, reason="campaign_not_paused")
                continue

        elif atype == "apply_discount_promotion":
            rev_delta = getattr(sales_report, "revenue_delta_pct", 0.0) if sales_report else 0.0
            if rev_delta >= -5.0:
                log.warning("synthesis.action_blocked", action_type=atype, reason="revenue_drop_below_threshold")
                continue

        clean.append(action)

    return clean


async def synthesis_node(state: GraphState) -> dict:
    """Merge domain reports into a RootCauseReport with validated proposed actions."""
    with _tracer.start_as_current_span("synthesis_node") as span:
        span.set_attribute("query_id", state.get("query_id", ""))
        span.set_attribute("intent", state.get("intent", "diagnose"))
        start = state.get("investigation_start_ms", int(time.time() * 1000))
        duration_ms = int(time.time() * 1000) - start

        reports_text: list[str] = []
        for domain, key in [
            ("Sales", "sales_report"),
            ("Inventory", "inventory_report"),
            ("Marketing", "marketing_report"),
            ("Support", "support_report"),
        ]:
            report = state.get(key)
            if not report:
                continue
            if key == "sales_report" and hasattr(report, "top_declining_category_names"):
                d = report.model_dump(mode="python")
                d["top_declining_categories"] = report.top_declining_category_names
                reports_text.append(
                    f"### {domain} Report\n{json.dumps(d, indent=2, default=str)}"
                )
            else:
                reports_text.append(f"### {domain} Report\n{report.model_dump_json(indent=2)}")

        reflection = state.get("reflection_result")
        evidence_score = reflection.evidence_score if reflection else 0.5

        memory = state.get("memory_context")
        memory_hint = ""
        if memory and getattr(memory, "kedb_entries", None):
            memory_hint = (
                "\n\n=== HISTORICAL REFERENCE ONLY — do NOT use for action parameters ==="
                f"\nSimilar past pattern: {memory.kedb_entries[0].get('root_cause', '')[:300]}"
                "\n=== END HISTORICAL REFERENCE ==="
            )

        try:
            kadb_context = _build_kadb_context()
        except Exception as exc:
            log.warning("synthesis.kadb_unavailable", error=str(exc))
            kadb_context = ""

        messages = [
            SystemMessage(content=_SYSTEM),
            HumanMessage(
                content=(
                    f"Query: {state['query']}\n"
                    f"Intent: {state.get('intent', 'diagnose')}\n"
                    f"Evidence score: {evidence_score}\n\n"
                )
                + "\n\n".join(reports_text)
                + memory_hint
                + kadb_context
                + f"\n\nInvestigation duration: {duration_ms}ms\n"
                + f"Return a RootCauseReport JSON with query_id='{state['query_id']}'."
            ),
        ]

        llm = synthesis_llm()
        structured_llm = llm.with_structured_output(RootCauseReport, method="function_calling")

        llm_start_ms = int(time.time() * 1000)
        try:
            report: RootCauseReport = await structured_llm.ainvoke(messages)
        except Exception as exc:
            log.error("synthesis.llm_failed", error=str(exc))
            span.record_exception(exc)
            span.set_attribute("error", True)
            return {
                "error": f"Synthesis failed: {exc!s}",
                "audit_log": [{"node": "synthesis", "event": "failed", "error": str(exc)[:200]}],
            }
        finally:
            safe_record(
                llm_latency_histogram,
                int(time.time() * 1000) - llm_start_ms,
                {"node": "synthesis"},
            )

        try:
            if len(report.proposed_actions) > _MAX_ACTIONS:
                log.warning(
                    "synthesis.actions_capped",
                    original=len(report.proposed_actions),
                    capped_to=_MAX_ACTIONS,
                )
                report.proposed_actions = report.proposed_actions[:_MAX_ACTIONS]

            inventory_report = state.get("inventory_report")
            marketing_report = state.get("marketing_report")
            sales_report_obj = state.get("sales_report")

            clean_actions = _filter_actions(
                report.proposed_actions, inventory_report, marketing_report, sales_report_obj
            )

            if len(clean_actions) < len(report.proposed_actions):
                log.info(
                    "synthesis.actions_filtered",
                    before=len(report.proposed_actions),
                    after=len(clean_actions),
                )

            if not _intent_allows_actions(state.get("intent")):
                if clean_actions:
                    log.info(
                        "synthesis.actions_suppressed",
                        intent=state.get("intent"),
                        suppressed=len(clean_actions),
                    )
                clean_actions = []

            report.proposed_actions = clean_actions

            enriched_actions: list[ProposedAction] = []
            for action in report.proposed_actions:
                stats = get_action_stats(action.action_type)
                enriched = ProposedAction(**action.model_dump())
                enriched.historical_success_rate = stats.get("success_rate")
                enriched_actions.append(enriched)
            report.proposed_actions = enriched_actions

            span.set_attribute("root_causes", len(report.root_causes))
            span.set_attribute("proposed_actions", len(report.proposed_actions))
            log.info(
                "synthesis.done",
                causes=len(report.root_causes),
                actions=len(report.proposed_actions),
            )

            return {
                "root_cause_report": report,
                "proposed_actions": [
                    {
                        "action_id": a.action_id,
                        "action_type": a.action_type,
                        "params": a.parameters,
                        "estimated_impact": a.estimated_impact or "",
                        "dry_run_result": None,
                        "kadb_success_rate": a.historical_success_rate,
                    }
                    for a in report.proposed_actions
                ],
                "audit_log": [
                    {
                        "node": "synthesis",
                        "event": "report_generated",
                        "root_causes": len(report.root_causes),
                        "evidence_score": evidence_score,
                    }
                ],
            }
        except Exception as exc:
            log.error("synthesis.postprocessing_failed", error=str(exc))
            span.record_exception(exc)
            span.set_attribute("error", True)
            return {
                "error": f"Synthesis post-processing failed: {exc!s}",
                "audit_log": [{"node": "synthesis", "event": "failed", "error": str(exc)[:200]}],
            }
