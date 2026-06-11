"""Action execution tools — all default to dry_run=True for safety."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import MockProduct
from ecommerce_brain.tools.registry import register_tool


class RestockProductInput(BaseModel):
    sku: str
    quantity: int = Field(ge=1, le=10000)
    dry_run: bool = Field(default=True)


class IncreaseCampaignBudgetInput(BaseModel):
    campaign_id: str
    increase_pct: float = Field(ge=1.0, le=200.0, description="Percentage increase")
    dry_run: bool = Field(default=True)


class ApplyDiscountInput(BaseModel):
    category: str
    discount_pct: float = Field(ge=1.0, le=50.0)
    dry_run: bool = Field(default=True)


@register_tool(args_schema=RestockProductInput)
def restock_product(sku: str, quantity: int, dry_run: bool = True) -> dict:
    """Place a restock order for a SKU. dry_run=True validates without executing."""
    with get_session() as session:
        product = session.get(MockProduct, sku)
        if not product:
            return {"success": False, "error": f"SKU {sku} not found", "dry_run": dry_run}

        current = product.current_stock
        new_stock = current + quantity
        estimated_cost = round(quantity * product.unit_cost, 2)

        result = {
            "sku": sku,
            "name": product.name,
            "current_stock": current,
            "qty_ordered": quantity,
            "new_stock_after": new_stock,
            "estimated_cost": estimated_cost,
            "dry_run": dry_run,
            "action": "restock_product",
        }

        if not dry_run:
            product.current_stock = new_stock
            result["success"] = True
            result["message"] = f"Restocked {sku}: {current} → {new_stock} units (ordered {quantity})"
        else:
            result["success"] = True
            result["message"] = (
                f"DRY RUN: Would restock {sku} from {current} to {new_stock} units."
                f" Cost: ${estimated_cost:,.2f}"
            )

    return result


@register_tool(args_schema=IncreaseCampaignBudgetInput)
def increase_campaign_budget(campaign_id: str, increase_pct: float, dry_run: bool = True) -> dict:
    """Increase daily budget for a campaign by given percentage."""
    from ecommerce_brain.db.models import MockCampaign

    with get_session() as session:
        campaign = session.get(MockCampaign, campaign_id)
        if not campaign:
            return {"success": False, "error": f"Campaign {campaign_id} not found", "dry_run": dry_run}  # noqa: E501

        new_budget = round(campaign.daily_budget * (1 + increase_pct / 100), 2)
        result = {
            "campaign_id": campaign_id,
            "name": campaign.name,
            "current_budget": campaign.daily_budget,
            "new_budget": new_budget,
            "increase_pct": increase_pct,
            "dry_run": dry_run,
            "action": "increase_campaign_budget",
        }

        if not dry_run:
            campaign.daily_budget = new_budget
            result["success"] = True
            result["message"] = f"Budget updated: ${campaign.daily_budget:,.2f} → ${new_budget:,.2f}/day"  # noqa: E501
        else:
            result["success"] = True
            result["message"] = (
                f"DRY RUN: Would increase budget from ${campaign.daily_budget:,.2f}"
                f" to ${new_budget:,.2f}/day"
            )

    return result


@register_tool(args_schema=ApplyDiscountInput)
def apply_discount_promotion(category: str, discount_pct: float, dry_run: bool = True) -> dict:
    """Apply a category-wide discount promotion."""
    result = {
        "category": category,
        "discount_pct": discount_pct,
        "dry_run": dry_run,
        "action": "apply_discount_promotion",
        "success": True,
    }
    if not dry_run:
        result["message"] = f"Applied {discount_pct}% discount to {category} category"
    else:
        result["message"] = (
            f"DRY RUN: Would apply {discount_pct}% discount to all {category} products"
        )
    return result
