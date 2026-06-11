"""Synthesis node — Coordinator LLM merges all domain reports → RootCauseReport."""

from __future__ import annotations

import json
import time

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from ecommerce_brain.graph.state import GraphState
from ecommerce_brain.llm import synthesis_llm
from ecommerce_brain.memory.kadb import get_action_stats
from ecommerce_brain.schemas.outputs import ProposedAction, RootCauseReport

log = structlog.get_logger(__name__)

# Hard cap on proposed actions regardless of LLM output.
_MAX_ACTIONS = 4

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

For root_causes: include exact metrics, domain, evidence, and confidence level.
The summary field must be 2-4 sentences covering all key findings with numbers.
Return only the RootCauseReport JSON — no prose.
"""


def _intent_allows_actions(intent: str | None) -> bool:
    return intent == "action"


async def synthesis_node(state: GraphState) -> dict:
    start = state.get("investigation_start_ms", int(time.time() * 1000))
    duration_ms = int(time.time() * 1000) - start

    reports_text = []
    for domain, key in [
        ("Sales", "sales_report"),
        ("Inventory", "inventory_report"),
        ("Marketing", "marketing_report"),
        ("Support", "support_report"),
    ]:
        report = state.get(key)
        if report:
            # For SalesReport, surface category names plainly so LLM doesn't receive dicts
            if key == "sales_report" and hasattr(report, "top_declining_category_names"):
                d = report.model_dump(mode="python")
                d["top_declining_categories"] = report.top_declining_category_names
                reports_text.append(f"### {domain} Report\n{json.dumps(d, indent=2, default=str)}")
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

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(
            content=f"Query: {state['query']}\nIntent: {state.get('intent', 'diagnose')}\nEvidence score: {evidence_score}\n\n"
            + "\n\n".join(reports_text)
            + memory_hint
            + f"\n\nInvestigation duration: {duration_ms}ms\n"
            + f"Return a RootCauseReport JSON with query_id='{state['query_id']}'."
        ),
    ]

    llm = synthesis_llm()
    structured_llm = llm.with_structured_output(RootCauseReport, method="function_calling")

    try:
        report: RootCauseReport = await structured_llm.ainvoke(messages)

        # Hard cap — never let the LLM propose more than _MAX_ACTIONS.
        if len(report.proposed_actions) > _MAX_ACTIONS:
            log.warning("synthesis.actions_capped", original=len(report.proposed_actions), capped_to=_MAX_ACTIONS)
            report.proposed_actions = report.proposed_actions[:_MAX_ACTIONS]

        # ── Hard post-processing: enforce data integrity in code, not just in the prompt ──
        # The LLM regularly violates data constraints when KEDB history is present.
        # These filters are the authoritative guard — LLM output is advisory only.
        inventory_report = state.get("inventory_report")
        marketing_report = state.get("marketing_report")
        sales_report_obj = state.get("sales_report")

        # Channel names the LLM confuses with campaign_id values
        _CHANNEL_NAMES = {"google", "meta", "email", "tiktok", "instagram", "facebook", "youtube", "bing"}

        valid_skus: set[str] = set()
        if inventory_report is not None:
            for item in getattr(inventory_report, "stockouts", []):
                valid_skus.add(getattr(item, "sku", ""))
            valid_skus.update(getattr(inventory_report, "near_stockout_skus", []))

        paused_campaign_ids: set[str] = set()
        if marketing_report is not None:
            for c in getattr(marketing_report, "paused_campaigns", []):
                paused_campaign_ids.add(getattr(c, "campaign_id", ""))

        clean_actions = []
        for action in report.proposed_actions:
            atype = action.action_type
            params = action.parameters

            if atype == "restock_product":
                sku = params.get("sku", "")
                if not valid_skus:
                    # Inventory report has zero stockouts/near-stockouts — no restocks allowed
                    log.warning("synthesis.action_blocked", action_type=atype, sku=sku, reason="no_stockouts_in_report")
                    continue
                if sku not in valid_skus:
                    log.warning("synthesis.action_blocked", action_type=atype, sku=sku, reason="sku_not_in_current_report")
                    continue

            elif atype == "increase_campaign_budget":
                cid = params.get("campaign_id", "")
                if cid.lower() in _CHANNEL_NAMES:
                    # LLM used channel name instead of campaign_id — block, don't guess
                    log.warning("synthesis.action_blocked", action_type=atype, reason="channel_name_used_as_id", value=cid)
                    continue
                if marketing_report is not None:
                    roas_delta = getattr(marketing_report, "roas_delta_pct", 0.0)
                    underperforming = getattr(marketing_report, "underperforming_channels", [])
                    if roas_delta >= -10.0 and not underperforming:
                        log.warning("synthesis.action_blocked", action_type=atype, reason="roas_acceptable_no_underperforming")
                        continue

            elif atype == "resume_campaign":
                if not paused_campaign_ids:
                    log.warning("synthesis.action_blocked", action_type=atype, reason="no_paused_campaigns")
                    continue
                if params.get("campaign_id") not in paused_campaign_ids:
                    log.warning("synthesis.action_blocked", action_type=atype, reason="campaign_id_not_in_paused_list")
                    continue

            elif atype == "apply_discount_promotion":
                rev_delta = getattr(sales_report_obj, "revenue_delta_pct", 0.0) if sales_report_obj else 0.0
                if rev_delta >= -5.0:
                    log.warning("synthesis.action_blocked", action_type=atype, reason="revenue_drop_below_threshold")
                    continue

            clean_actions.append(action)

        if len(clean_actions) < len(report.proposed_actions):
            log.info(
                "synthesis.actions_filtered",
                before=len(report.proposed_actions),
                after=len(clean_actions),
            )

        if not _intent_allows_actions(state.get("intent")):
            if clean_actions:
                log.info(
                    "synthesis.actions_suppressed_non_action_intent",
                    intent=state.get("intent"),
                    suppressed=len(clean_actions),
                )
            clean_actions = []

        report.proposed_actions = clean_actions

        # Enrich proposed actions with KADB success rates
        enriched_actions = []
        for action in report.proposed_actions:
            stats = get_action_stats(action.action_type)
            enriched = ProposedAction(**action.model_dump())
            enriched.historical_success_rate = stats.get("success_rate")
            enriched_actions.append(enriched)
        report.proposed_actions = enriched_actions

        log.info("synthesis.done", causes=len(report.root_causes), actions=len(report.proposed_actions))  # noqa: E501

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
        log.error("synthesis.failed", error=str(exc))
        return {
            "error": f"Synthesis failed: {exc!s}",
            "audit_log": [{"node": "synthesis", "event": "failed", "error": str(exc)[:200]}],
        }
