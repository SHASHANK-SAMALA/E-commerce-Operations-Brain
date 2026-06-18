import logging

from mcp.server.fastmcp import FastMCP

from ecommerce_brain.tools.inventory_tools import (
    get_restock_candidates as _get_restock_candidates,
)
from ecommerce_brain.tools.inventory_tools import (
    get_stock_levels as _get_stock_levels,
)
from ecommerce_brain.tools.inventory_tools import (
    get_stockout_products as _get_stockout_products,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inventory_mcp_server")

mcp = FastMCP("inventory-mcp-server", port=8002, host="0.0.0.0")  # nosec B104

@mcp.tool()
def get_stock_levels(skus: list[str] | None = None) -> list[dict]:
    """Get current stock levels, reorder points, and days-of-supply for products."""
    return _get_stock_levels(skus=skus)

@mcp.tool()
def get_stockout_products(include_near_stockout: bool = True) -> dict:
    """Return products currently out-of-stock and near-stockout SKUs."""
    return _get_stockout_products(include_near_stockout=include_near_stockout)

@mcp.tool()
def get_restock_candidates(top_n: int = 10) -> list[dict]:
    """Return top restock candidates sorted by urgency (revenue impact)."""
    return _get_restock_candidates(top_n=top_n)

if __name__ == "__main__":
    logger.info("Starting Inventory MCP Server on port 8002...")
    mcp.run(transport="sse")
