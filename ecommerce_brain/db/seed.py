"""Seed script — creates tables and inserts realistic mock e-commerce dataset.

Run: python -m ecommerce_brain.db.seed
With embeddings: python -m ecommerce_brain.db.seed --embeddings
"""

from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from faker import Faker
from sqlalchemy import select, text

from ecommerce_brain.db.engine import Base, engine, get_session
from ecommerce_brain.db.models import (
    KADBEntry,
    KEDBEntry,
    MockCampaign,
    MockProduct,
    MockSalesMetric,
    MockSupportTicket,
)

fake = Faker()
Faker.seed(42)
random.seed(42)

# ── Products (30 SKUs across 6 categories) ────────────────────────────────────
# SKUs must remain stable — tools query by these exact identifiers
PRODUCTS = [
    # Electronics
    {"sku": "ELEC-001", "name": "Wireless Earbuds Pro", "category": "Electronics", "current_stock": 0, "reorder_point": 100, "unit_cost": 45.0, "avg_daily_sales": 28.5},
    {"sku": "ELEC-002", "name": "Smart Watch Series 5", "category": "Electronics", "current_stock": 12, "reorder_point": 50, "unit_cost": 180.0, "avg_daily_sales": 15.2},
    {"sku": "ELEC-003", "name": "Portable Charger 20000mAh", "category": "Electronics", "current_stock": 234, "reorder_point": 80, "unit_cost": 22.0, "avg_daily_sales": 42.0},
    {"sku": "ELEC-004", "name": "Bluetooth Speaker Mini", "category": "Electronics", "current_stock": 0, "reorder_point": 60, "unit_cost": 35.0, "avg_daily_sales": 19.8},
    {"sku": "ELEC-005", "name": "USB-C Hub 7-in-1", "category": "Electronics", "current_stock": 88, "reorder_point": 40, "unit_cost": 28.0, "avg_daily_sales": 11.3},
    # Apparel
    {"sku": "APP-001", "name": "Performance Running Jacket", "category": "Apparel", "current_stock": 45, "reorder_point": 30, "unit_cost": 55.0, "avg_daily_sales": 8.7},
    {"sku": "APP-002", "name": "Yoga Pants Premium", "category": "Apparel", "current_stock": 120, "reorder_point": 40, "unit_cost": 30.0, "avg_daily_sales": 22.1},
    {"sku": "APP-003", "name": "Casual Hoodie Unisex", "category": "Apparel", "current_stock": 0, "reorder_point": 50, "unit_cost": 25.0, "avg_daily_sales": 18.4},
    {"sku": "APP-004", "name": "Athletic T-Shirt Pack 3x", "category": "Apparel", "current_stock": 67, "reorder_point": 35, "unit_cost": 20.0, "avg_daily_sales": 14.6},
    {"sku": "APP-005", "name": "Winter Parka Insulated", "category": "Apparel", "current_stock": 33, "reorder_point": 20, "unit_cost": 95.0, "avg_daily_sales": 5.2},
    # Home & Kitchen
    {"sku": "HOME-001", "name": "Air Purifier HEPA H13", "category": "Home", "current_stock": 18, "reorder_point": 25, "unit_cost": 120.0, "avg_daily_sales": 7.3},
    {"sku": "HOME-002", "name": "Coffee Maker Drip 12-Cup", "category": "Home", "current_stock": 55, "reorder_point": 30, "unit_cost": 45.0, "avg_daily_sales": 9.8},
    {"sku": "HOME-003", "name": "Non-Stick Cookware Set 5pc", "category": "Home", "current_stock": 0, "reorder_point": 20, "unit_cost": 75.0, "avg_daily_sales": 6.1},
    {"sku": "HOME-004", "name": "Robot Vacuum Slim", "category": "Home", "current_stock": 7, "reorder_point": 15, "unit_cost": 200.0, "avg_daily_sales": 4.5},
    {"sku": "HOME-005", "name": "Bamboo Cutting Board Set", "category": "Home", "current_stock": 190, "reorder_point": 40, "unit_cost": 18.0, "avg_daily_sales": 12.0},
    # Sports
    {"sku": "SPORT-001", "name": "Resistance Bands Set 5-Pack", "category": "Sports", "current_stock": 0, "reorder_point": 80, "unit_cost": 15.0, "avg_daily_sales": 35.2},
    {"sku": "SPORT-002", "name": "Foam Roller Deep Tissue", "category": "Sports", "current_stock": 143, "reorder_point": 50, "unit_cost": 22.0, "avg_daily_sales": 17.9},
    {"sku": "SPORT-003", "name": "Yoga Mat Non-Slip 6mm", "category": "Sports", "current_stock": 88, "reorder_point": 60, "unit_cost": 28.0, "avg_daily_sales": 24.3},
    {"sku": "SPORT-004", "name": "Adjustable Dumbbell 25lb", "category": "Sports", "current_stock": 4, "reorder_point": 20, "unit_cost": 85.0, "avg_daily_sales": 6.8},
    {"sku": "SPORT-005", "name": "Water Bottle Insulated 32oz", "category": "Sports", "current_stock": 267, "reorder_point": 100, "unit_cost": 20.0, "avg_daily_sales": 38.6},
    # Beauty
    {"sku": "BEAU-001", "name": "Vitamin C Serum 30ml", "category": "Beauty", "current_stock": 0, "reorder_point": 120, "unit_cost": 18.0, "avg_daily_sales": 45.0},
    {"sku": "BEAU-002", "name": "Hyaluronic Acid Moisturizer", "category": "Beauty", "current_stock": 34, "reorder_point": 80, "unit_cost": 22.0, "avg_daily_sales": 31.4},
    {"sku": "BEAU-003", "name": "Electric Face Cleansing Brush", "category": "Beauty", "current_stock": 56, "reorder_point": 40, "unit_cost": 35.0, "avg_daily_sales": 12.7},
    {"sku": "BEAU-004", "name": "SPF 50 Sunscreen Tinted", "category": "Beauty", "current_stock": 123, "reorder_point": 60, "unit_cost": 14.0, "avg_daily_sales": 28.9},
    {"sku": "BEAU-005", "name": "Retinol Eye Cream Premium", "category": "Beauty", "current_stock": 8, "reorder_point": 30, "unit_cost": 40.0, "avg_daily_sales": 10.2},
    # Pet
    {"sku": "PET-001", "name": "Premium Dog Food Grain-Free 5kg", "category": "Pet", "current_stock": 78, "reorder_point": 50, "unit_cost": 38.0, "avg_daily_sales": 22.5},
    {"sku": "PET-002", "name": "Cat Tree Tower Deluxe", "category": "Pet", "current_stock": 0, "reorder_point": 15, "unit_cost": 65.0, "avg_daily_sales": 5.8},
    {"sku": "PET-003", "name": "Automatic Pet Feeder Smart", "category": "Pet", "current_stock": 23, "reorder_point": 20, "unit_cost": 55.0, "avg_daily_sales": 7.2},
    {"sku": "PET-004", "name": "Dog Leash Retractable 5m", "category": "Pet", "current_stock": 145, "reorder_point": 40, "unit_cost": 12.0, "avg_daily_sales": 16.3},
    {"sku": "PET-005", "name": "Interactive Cat Toy Set", "category": "Pet", "current_stock": 91, "reorder_point": 30, "unit_cost": 16.0, "avg_daily_sales": 13.1},
]

# ── Campaigns ─────────────────────────────────────────────────────────────────
CAMPAIGNS = [
    {"campaign_id": "CAM-001", "name": "Summer Electronics Sale", "channel": "google", "status": "active", "daily_budget": 2500.0, "roas": 4.2, "paused_at": None},
    {"campaign_id": "CAM-002", "name": "Beauty Essentials Push", "channel": "meta", "status": "active", "daily_budget": 1800.0, "roas": 3.8, "paused_at": None},
    {"campaign_id": "CAM-003", "name": "Sports & Fitness Promo", "channel": "google", "status": "paused", "daily_budget": 3200.0, "roas": 0.0, "paused_at": "2026-06-01T14:30:00"},
    {"campaign_id": "CAM-004", "name": "Home Appliance Deals", "channel": "email", "status": "active", "daily_budget": 400.0, "roas": 6.1, "paused_at": None},
    {"campaign_id": "CAM-005", "name": "Pet Lovers Weekend", "channel": "meta", "status": "paused", "daily_budget": 900.0, "roas": 0.0, "paused_at": "2026-06-02T09:15:00"},
    {"campaign_id": "CAM-006", "name": "Apparel Flash Sale", "channel": "google", "status": "active", "daily_budget": 1500.0, "roas": 2.9, "paused_at": None},
    {"campaign_id": "CAM-007", "name": "Retargeting - Cart Abandoners", "channel": "meta", "status": "active", "daily_budget": 800.0, "roas": 5.4, "paused_at": None},
    {"campaign_id": "CAM-008", "name": "New Customer Acquisition", "channel": "google", "status": "paused", "daily_budget": 2100.0, "roas": 0.0, "paused_at": "2026-06-02T18:45:00"},
    {"campaign_id": "CAM-009", "name": "Loyalty Rewards Email Blast", "channel": "email", "status": "active", "daily_budget": 320.0, "roas": 7.8, "paused_at": None},
    {"campaign_id": "CAM-010", "name": "TikTok Viral Product Push", "channel": "tiktok", "status": "paused", "daily_budget": 1200.0, "roas": 0.0, "paused_at": "2026-06-01T22:00:00"},
    {"campaign_id": "CAM-011", "name": "Influencer Beauty Collab", "channel": "meta", "status": "active", "daily_budget": 950.0, "roas": 4.6, "paused_at": None},
    {"campaign_id": "CAM-012", "name": "Weekend Deal Blitz", "channel": "google", "status": "active", "daily_budget": 1750.0, "roas": 3.3, "paused_at": None},
]

# ── Sales metrics ─────────────────────────────────────────────────────────────
REGIONS = ["North", "South", "East", "West"]
CATEGORIES = ["Electronics", "Apparel", "Home", "Sports", "Beauty", "Pet"]

_CATEGORY_BASE = {
    "Electronics": (8000, 18000),
    "Apparel": (5000, 12000),
    "Home": (4000, 9000),
    "Sports": (5500, 11000),
    "Beauty": (6000, 14000),
    "Pet": (3000, 7000),
}
_CATEGORY_ORDERS = {
    "Electronics": (60, 180),
    "Apparel": (80, 220),
    "Home": (40, 120),
    "Sports": (70, 190),
    "Beauty": (100, 260),
    "Pet": (50, 140),
}


def _generate_sales_metrics() -> list[dict]:
    rows = []
    today = date.today()
    for days_ago in range(30, 0, -1):
        d = today - timedelta(days=days_ago)
        date_str = d.isoformat()
        is_weekend = d.weekday() >= 5
        is_recent_drop = days_ago <= 3
        day_factor = (1.15 if is_weekend else 1.0) * (0.78 if is_recent_drop else 1.0)
        for region in REGIONS:
            region_factor = {"North": 1.0, "South": 0.88, "East": 1.12, "West": 0.95}[region]
            for cat in CATEGORIES:
                base_rev = random.uniform(*_CATEGORY_BASE[cat])
                base_orders = random.randint(*_CATEGORY_ORDERS[cat])
                noise_rev = random.uniform(-300, 300)
                noise_ord = random.randint(-15, 15)
                rev = round(base_rev * day_factor * region_factor + noise_rev, 2)
                orders = max(1, int(base_orders * day_factor * region_factor + noise_ord))
                rows.append({
                    "date": date_str,
                    "revenue": rev,
                    "orders": orders,
                    "aov": round(rev / orders, 2),
                    "region": region,
                    "category": cat,
                })
    return rows


# ── Support tickets ────────────────────────────────────────────────────────────
ISSUE_TYPES = ["out_of_stock", "shipping_delay", "product_defect", "wrong_item", "billing_issue", "return_request"]


def _ticket_summary(issue: str, sku: str | None) -> str:
    """Generate a realistic Faker-based customer complaint message."""
    product_name = next(
        (p["name"] for p in PRODUCTS if p["sku"] == sku), "the item"
    ) if sku else "the item"
    order_id = f"ORD-{fake.numerify('######')}"

    templates = {
        "out_of_stock": [
            f"Hi, I placed order {order_id} for {product_name} three days ago and just got an email saying it's out of stock. I need this urgently - can you expedite a restock or offer an alternative?",
            f"My order {order_id} was confirmed but now shows 'unavailable'. {product_name} was listed as in-stock when I purchased. This is really frustrating.",
            f"I've been waiting {random.randint(3,7)} days for {product_name} (order {order_id}). The website still shows it as available but I keep getting cancellation notices.",
            f"Ordered {product_name} as a gift (order {order_id}) and was told it's out of stock AFTER the payment cleared. Please help.",
        ],
        "shipping_delay": [
            f"Order {order_id} was supposed to arrive by {fake.date_between(start_date='-5d', end_date='-1d')} but tracking shows it's been stuck at the {fake.city()} facility for {random.randint(2,5)} days.",
            f"My package ({order_id}) hasn't moved in {random.randint(3,6)} days. The carrier says to contact the sender. This was a time-sensitive order.",
            f"Tracking for {order_id} shows 'in transit' since {fake.date_between(start_date='-8d', end_date='-4d')}. Estimated delivery has passed. Where is my order?",
            f"I paid for express shipping on {order_id} but it's been {random.randint(5,9)} business days. I want a refund on the shipping cost.",
        ],
        "product_defect": [
            f"Received {product_name} (order {order_id}) but it stopped working after just {random.randint(1,4)} days. The unit appears defective. Requesting replacement.",
            f"The {product_name} I received is clearly not functioning as advertised. Order {order_id}.",
            f"Unboxed my {product_name} from order {order_id} and it was already broken. Looks like it was returned and resold. Very disappointed.",
            f"Quality issue with {product_name} (order {order_id}). Expecting a full refund or exchange.",
        ],
        "wrong_item": [
            f"Received the wrong item in order {order_id}. I ordered {product_name} but got something completely different. Please send the correct item ASAP.",
            f"Order {order_id} contained the wrong variant - I ordered {product_name} but received a different model.",
            f"My order {order_id} is missing {product_name}. The box was incomplete.",
            f"Someone else's order was mixed into mine (order {order_id}). I have items I didn't order and am missing {product_name}.",
        ],
        "billing_issue": [
            f"I was charged twice for order {order_id} - both transactions show on my card. Please refund the duplicate charge immediately.",
            f"My discount code wasn't applied to order {order_id} despite showing as valid at checkout. I should have received a discount.",
            f"Requested a refund for order {order_id} on {fake.date_between(start_date='-10d', end_date='-5d')} and it still hasn't appeared.",
            f"I was charged more than the price shown at checkout for order {order_id}. No explanation in the invoice.",
        ],
        "return_request": [
            f"I'd like to return {product_name} from order {order_id}. It doesn't fit my needs. How do I initiate a return? I couldn't find the prepaid label.",
            f"Returning {product_name} (order {order_id}) - unused, still in original packaging. It was a gift duplicate.",
            f"I need to return {product_name} (order {order_id}) within the return window. The return portal shows an error.",
            f"Can I return {product_name} from order {order_id}? I bought it {random.randint(5,25)} days ago and haven't opened it yet.",
        ],
    }
    return random.choice(templates[issue])


def _generate_support_tickets() -> list[dict]:
    rows = []
    today = date.today()
    for days_ago in range(25, 0, -1):
        d = today - timedelta(days=days_ago)
        date_str = d.isoformat()
        count = random.randint(12, 20) if days_ago > 3 else random.randint(28, 45)
        for _ in range(count):
            if days_ago <= 3:
                issue = random.choice(["out_of_stock", "out_of_stock", "shipping_delay", "product_defect", "return_request"])
            else:
                issue = random.choice(ISSUE_TYPES)
            sku = random.choice(PRODUCTS)["sku"] if issue in ("out_of_stock", "product_defect", "wrong_item") else None
            rows.append({
                "date": date_str,
                "issue_type": issue,
                "sku": sku,
                "sentiment_score": round(
                    random.uniform(0.05, 0.38) if days_ago <= 3 else random.uniform(0.28, 0.82), 2
                ),
                "is_refund": issue in ("billing_issue", "return_request"),
                "summary": _ticket_summary(issue, sku),
            })
    return rows


# ── KEDB seed entries ─────────────────────────────────────────────────────────
KEDB_ENTRIES = [
    {
        "symptom_summary": "Revenue drop 15-25% coinciding with stockout of top-selling SKUs and paused Google Ads campaign",
        "root_cause": "Dual failure: inventory depletion of high-velocity SKUs (ELEC-001, SPORT-001) combined with automated campaign pause triggered by ROAS threshold breach caused a compounded 22% revenue drop.",
        "resolution_steps": ["Emergency restock order for top 5 OOS SKUs", "Resume paused campaigns with increased daily budget", "Monitor ROAS for 48h before reducing budget again"],
        "affected_domains": ["sales", "inventory", "marketing"],
        "occurrence_count": 3,
    },
    {
        "symptom_summary": "Customer complaint spike +40% with simultaneous increase in out-of-stock tickets",
        "root_cause": "Inventory system failed to update stock levels after warehouse transfer, causing 6 SKUs to display in-stock while physically unavailable. Resulted in 340 customer complaints and 89 refunds.",
        "resolution_steps": ["Force inventory sync from warehouse WMS", "Bulk cancel unfulfillable orders with apology email", "Issue 10% discount to affected customers"],
        "affected_domains": ["inventory", "support"],
        "occurrence_count": 2,
    },
    {
        "symptom_summary": "AOV dropped 18% while order volume held steady — regional anomaly in Western region",
        "root_cause": "High-margin Electronics category unavailable in West region due to regional warehouse allocation error. Orders shifted to lower-margin Apparel and Pet categories.",
        "resolution_steps": ["Rebalance warehouse allocation for Electronics", "Apply regional promotion for Electronics to recover AOV"],
        "affected_domains": ["sales", "inventory"],
        "occurrence_count": 1,
    },
    {
        "symptom_summary": "Marketing ROAS collapsed from 4.2 to 0.8 overnight",
        "root_cause": "Meta ad account flagged for policy violation (automated false positive). All Meta campaigns paused simultaneously. Google spend not increased to compensate.",
        "resolution_steps": ["Appeal Meta account flag (SLA: 24h)", "Shift 60% of Meta budget to Google temporarily", "Email campaign to existing customer base as bridge"],
        "affected_domains": ["marketing", "sales"],
        "occurrence_count": 4,
    },
    {
        "symptom_summary": "Sales drop isolated to Beauty category, other categories unaffected",
        "root_cause": "Top Beauty influencer partnership ended. Organic traffic from influencer links dropped 65%. BEAU-001 (Vitamin C Serum) was 34% of Beauty revenue.",
        "resolution_steps": ["Activate 20% discount promotion for Beauty", "Reach out to 3 alternative influencer partners", "Boost paid search for BEAU-001 search terms"],
        "affected_domains": ["marketing", "sales"],
        "occurrence_count": 2,
    },
    {
        "symptom_summary": "Refund rate surged to 18% across Electronics — 3x above baseline",
        "root_cause": "Batch of ELEC-002 (Smart Watch Series 5) shipped with a firmware defect causing battery drain within 24h of setup. Affected ~400 units from warehouse lot WH-2026-05.",
        "resolution_steps": ["Issue proactive recall notice to affected customers", "Ship replacement units with expedited shipping", "Coordinate with supplier for root cause analysis", "Offer $25 store credit to affected customers"],
        "affected_domains": ["support", "inventory"],
        "occurrence_count": 1,
    },
    {
        "symptom_summary": "Checkout conversion rate fell 12% with no change in traffic or product availability",
        "root_cause": "Payment gateway timeout errors during peak hours caused 1 in 8 checkout attempts to fail silently. Customers abandoned rather than retry.",
        "resolution_steps": ["Escalate to payment processor for SLA breach", "Add retry logic with user-visible error messaging", "Enable backup payment gateway for peak hours"],
        "affected_domains": ["sales"],
        "occurrence_count": 2,
    },
]

KADB_ENTRIES = [
    {"action_type": "restock_product", "context_tags": ["stockout", "high_velocity"], "total_executions": 47, "successful_executions": 43, "avg_revenue_impact": 18500.0},
    {"action_type": "resume_campaign", "context_tags": ["paused_campaign", "roas_recovery"], "total_executions": 34, "successful_executions": 31, "avg_revenue_impact": 12200.0},
    {"action_type": "increase_campaign_budget", "context_tags": ["low_impressions", "revenue_drop"], "total_executions": 28, "successful_executions": 22, "avg_revenue_impact": 7800.0},
    {"action_type": "apply_discount_promotion", "context_tags": ["low_conversion", "cart_abandonment"], "total_executions": 19, "successful_executions": 14, "avg_revenue_impact": 5400.0},
    {"action_type": "send_customer_apology_email", "context_tags": ["complaint_spike", "oos_orders"], "total_executions": 12, "successful_executions": 11, "avg_revenue_impact": 2100.0},
]


def create_tables() -> None:
    print("Creating tables...")
    Base.metadata.create_all(engine)
    print("Tables created")


def seed_data() -> None:
    print("Seeding mock data...")
    sales_rows = _generate_sales_metrics()
    ticket_rows = _generate_support_tickets()
    with get_session() as session:
        for tbl in ["mock_support_tickets", "mock_campaigns", "mock_sales_metrics", "mock_products", "kadb", "kedb"]:
            session.execute(text(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE"))

        for p in PRODUCTS:
            session.add(MockProduct(**p))
        for c in CAMPAIGNS:
            session.add(MockCampaign(**c))
        for row in sales_rows:
            session.add(MockSalesMetric(**row))
        for row in ticket_rows:
            session.add(MockSupportTicket(**row))
        for e in KEDB_ENTRIES:
            session.add(KEDBEntry(**e))
        for e in KADB_ENTRIES:
            session.add(KADBEntry(**e))

    print(f"{len(PRODUCTS)} products, {len(CAMPAIGNS)} campaigns seeded")
    print(f"{len(sales_rows)} sales metrics rows seeded")
    print(f"{len(ticket_rows)} support tickets seeded")
    print(f"{len(KEDB_ENTRIES)} KEDB entries, {len(KADB_ENTRIES)} KADB entries seeded")


def seed_embeddings() -> None:
    print("Generating KEDB embeddings...")
    from ecommerce_brain.llm import embedding_client
    client = embedding_client()
    with get_session() as session:
        entries = session.scalars(select(KEDBEntry)).all()
        for entry in entries:
            vec = client.embed_query(entry.symptom_summary)
            entry.embedding = vec
    print(f"Embeddings generated for {len(entries)} KEDB entries")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings", action="store_true", help="Generate embeddings")
    args = parser.parse_args()

    create_tables()
    seed_data()
    if args.embeddings:
        seed_embeddings()
    print("Seed complete")
