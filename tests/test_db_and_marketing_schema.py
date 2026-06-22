"""Regression tests for DB bootstrap and marketing schema normalization."""

from __future__ import annotations

from sqlalchemy import inspect

from ecommerce_brain.db.engine import engine, initialize_database
from ecommerce_brain.schemas.outputs import InventoryReport, MarketingReport


def test_initialize_database_creates_incidents_table():
    initialize_database()

    inspector = inspect(engine)
    assert "incidents" in inspector.get_table_names()


def test_marketing_report_coerces_null_roas_delta():
    report = MarketingReport.model_validate(
        {
            "domain": "marketing",
            "paused_campaigns": [],
            "underperforming_channels": [],
            "missed_promotions": [],
            "roas_delta_pct": None,
            "total_paused_spend": 0.0,
        }
    )

    assert report.roas_delta_pct == 0.0


def test_inventory_report_coerces_stockout_numeric_strings():
    report = InventoryReport.model_validate(
        {
            "domain": "inventory",
            "stockouts": [
                {
                    "sku": "ELEC-001",
                    "name": "Wireless Earbuds Pro",
                    "time_oos_hours": "36 hours",
                    "impressions_lost": "1,250 impressions",
                    "suggested_restock_qty": "300 units",
                }
            ],
            "near_stockout_skus": [],
            "revenue_impact_estimate": 0.0,
            "restock_urgency": "HIGH",
        }
    )

    item = report.stockouts[0]
    assert item.time_oos_hours == 36.0
    assert item.impressions_lost == 1250
    assert item.suggested_restock_qty == 300