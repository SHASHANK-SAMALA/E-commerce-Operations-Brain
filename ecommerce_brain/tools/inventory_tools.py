"""Inventory domain tools."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from ecommerce_brain.db.engine import get_session
from ecommerce_brain.db.models import MockProduct
from ecommerce_brain.tools.registry import register_tool


class GetStockLevelsInput(BaseModel):
    skus: list[str] = Field(default_factory=list, description="SKU list; empty = all products")


class GetStockoutProductsInput(BaseModel):
    include_near_stockout: bool = Field(
        default=True, description="Include SKUs with stock < reorder_point"
    )


class GetRestockCandidatesInput(BaseModel):
    top_n: int = Field(default=10, ge=1, le=50)


@register_tool(args_schema=GetStockLevelsInput)
def get_stock_levels(skus: list[str] | None = None) -> list[dict]:
    """Get current stock levels, reorder points, and days-of-supply for products."""
    with get_session() as session:
        stmt = select(MockProduct)
        if skus:
            stmt = stmt.where(MockProduct.sku.in_(skus))
        products = session.scalars(stmt).all()
        return [
            {
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "current_stock": p.current_stock,
                "reorder_point": p.reorder_point,
                "days_of_supply": round(p.current_stock / max(p.avg_daily_sales, 0.1), 1),
                "status": (
                    "OOS" if p.current_stock == 0
                    else ("LOW" if p.current_stock < p.reorder_point else "OK")
                ),
            }
            for p in products
        ]


@register_tool(args_schema=GetStockoutProductsInput)
def get_stockout_products(include_near_stockout: bool = True) -> dict:
    """Return products currently out-of-stock and near-stockout SKUs."""
    with get_session() as session:
        oos = session.scalars(select(MockProduct).where(MockProduct.current_stock == 0)).all()
        near = (
            session.scalars(
                select(MockProduct).where(
                    MockProduct.current_stock > 0,
                    MockProduct.current_stock < MockProduct.reorder_point,
                )
            ).all()
            if include_near_stockout
            else []
        )
        return {
            "stockouts": [
                {
                    "sku": p.sku,
                    "name": p.name,
                    "category": p.category,
                    "avg_daily_sales": p.avg_daily_sales,
                    "estimated_revenue_loss_per_day": round(
                        p.avg_daily_sales * p.unit_cost * 2.5, 2
                    ),
                }
                for p in oos
            ],
            "near_stockout": [
                {
                    "sku": p.sku,
                    "name": p.name,
                    "current_stock": p.current_stock,
                    "days_of_supply": round(p.current_stock / max(p.avg_daily_sales, 0.1), 1),
                }
                for p in near
            ],
            "total_oos_count": len(oos),
            "total_near_oos_count": len(near),
        }


@register_tool(args_schema=GetRestockCandidatesInput)
def get_restock_candidates(top_n: int = 10) -> list[dict]:
    """Return top restock candidates sorted by urgency (revenue impact)."""
    with get_session() as session:
        products = session.scalars(
            select(MockProduct).where(MockProduct.current_stock < MockProduct.reorder_point)
        ).all()
        candidates = sorted(
            products,
            key=lambda p: p.avg_daily_sales * p.unit_cost,
            reverse=True,
        )[:top_n]
        return [
            {
                "sku": p.sku,
                "name": p.name,
                "current_stock": p.current_stock,
                "reorder_point": p.reorder_point,
                "suggested_qty": max(0, p.reorder_point * 3 - p.current_stock),
                "estimated_cost": round(
                    max(0, p.reorder_point * 3 - p.current_stock) * p.unit_cost, 2
                ),
                "priority": "CRITICAL" if p.current_stock == 0 else "HIGH",
            }
            for p in candidates
        ]
