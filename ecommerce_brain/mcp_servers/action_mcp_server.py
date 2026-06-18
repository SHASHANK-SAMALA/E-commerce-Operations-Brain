import logging

from mcp.server.fastmcp import FastMCP

from ecommerce_brain.tools.action_tools import (
    apply_discount_promotion as _apply_discount_promotion,
)
from ecommerce_brain.tools.action_tools import (
    increase_campaign_budget as _increase_campaign_budget,
)
from ecommerce_brain.tools.action_tools import (
    restock_product as _restock_product,
)
from ecommerce_brain.tools.action_tools import (
    resume_campaign as _resume_campaign,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("action_mcp_server")

mcp = FastMCP("action-mcp-server", port=8005, host="0.0.0.0")  # nosec B104

@mcp.tool()
def restock_product(sku: str, quantity: int, dry_run: bool = True) -> dict:
    """Place a restock order for a SKU. dry_run=True validates without executing."""
    return _restock_product(sku=sku, quantity=quantity, dry_run=dry_run)

@mcp.tool()
def increase_campaign_budget(campaign_id: str, increase_pct: float, dry_run: bool = True) -> dict:
    """Increase daily budget for a campaign by given percentage."""
    return _increase_campaign_budget(
        campaign_id=campaign_id, increase_pct=increase_pct, dry_run=dry_run
    )

@mcp.tool()
def apply_discount_promotion(category: str, discount_pct: float, dry_run: bool = True) -> dict:
    """Apply a category-wide discount promotion."""
    return _apply_discount_promotion(category=category, discount_pct=discount_pct, dry_run=dry_run)

@mcp.tool()
def resume_campaign(campaign_id: str, dry_run: bool = True) -> dict:
    """Resume a paused campaign. dry_run=True (default) — validate only, don't execute."""
    return _resume_campaign(campaign_id=campaign_id, dry_run=dry_run)

if __name__ == "__main__":
    logger.info("Starting Action MCP Server on port 8005...")
    mcp.run(transport="sse")
