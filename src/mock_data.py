"""
Hardcoded mock data standing in for a real backend / database.

This is intentionally tiny. The assignment is about the agent that sits
on top of tools, not about the data layer.
"""

ORDERS = {
    "ORD1001": {
        "order_id": "ORD1001",
        "buyer": "Aisha Khan",
        "seller_id": "SEL01",
        "item": "Wireless Mouse",
        "status": "shipped",
        "shipped_date": "2026-08-05",
        "expected_delivery": "2026-08-12",
        "amount_usd": 24.99,
    },
    "ORD1002": {
        "order_id": "ORD1002",
        "buyer": "Ravi Menon",
        "seller_id": "SEL02",
        "item": "Bluetooth Headphones",
        "status": "delayed",
        "shipped_date": None,
        "expected_delivery": "2026-08-15",
        "amount_usd": 59.99,
        "delay_reason": "seller reported inventory shortage",
    },
    "ORD1003": {
        "order_id": "ORD1003",
        "buyer": "Maria Lopez",
        "seller_id": "SEL01",
        "item": "USB-C Cable (3-pack)",
        "status": "delivered",
        "shipped_date": "2026-07-28",
        "expected_delivery": "2026-08-02",
        "delivered_date": "2026-08-01",
        "amount_usd": 12.50,
    },
    # ORD1999 intentionally does not exist, used to test "not found" handling
    # ORD_ERROR triggers a simulated backend failure, used to test tool-error handling
}

SELLERS = {
    "SEL01": {
        "seller_id": "SEL01",
        "name": "GadgetHub Store",
        "joined": "2023-01-10",
        "rating_avg": 4.6,
        "total_orders": 812,
    },
    "SEL02": {
        "seller_id": "SEL02",
        "name": "AudioWorld",
        "joined": "2024-05-22",
        "rating_avg": 2.9,
        "total_orders": 143,
    },
}

REVIEWS = {
    "SEL01": [
        {"review_id": "REV001", "rating": 5, "text": "Fast shipping, great product.", "date": "2026-07-30"},
        {"review_id": "REV002", "rating": 4, "text": "Good quality, packaging could be better.", "date": "2026-07-20"},
    ],
    "SEL02": [
        {"review_id": "REV010", "rating": 1, "text": "Order never arrived, no response from seller.", "date": "2026-08-01"},
        {"review_id": "REV011", "rating": 2, "text": "Item took 3 weeks to ship.", "date": "2026-07-15"},
        {"review_id": "REV012", "rating": 3, "text": "Product was fine but shipping was slow.", "date": "2026-06-30"},
    ],
    # SEL03 has no reviews on file -> used to test the "empty result" path
}
