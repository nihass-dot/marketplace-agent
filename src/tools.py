"""
Tool layer: the only place the agent is allowed to get facts from.

Each tool:
  - takes plain arguments
  - returns a plain dict, always with an "ok" flag
  - never raises for expected conditions (not found, empty) — it returns
    a structured result instead, so the agent loop has one consistent
    shape to reason about.
  - CAN raise for unexpected conditions (simulated backend outage), so we
    can prove the agent loop handles real exceptions too.

This is what "grounded" is built on: the agent is never allowed to state
a fact that didn't come out of one of these functions.
"""

from src.mock_data import ORDERS, SELLERS, REVIEWS


class ToolExecutionError(Exception):
    """Raised for unexpected tool failures (simulated backend outage, etc.)."""


def lookup_order(order_id: str) -> dict:
    if not isinstance(order_id, str) or not order_id.strip():
        return {"ok": False, "error": "invalid_argument", "message": "order_id must be a non-empty string"}

    order_id = order_id.strip().upper()

    # Simulate a downstream backend outage for a specific id, so we can
    # demonstrate the agent handling a hard tool failure, not just "not found".
    if order_id == "ORD_ERROR":
        raise ToolExecutionError("orders-service returned 500")

    order = ORDERS.get(order_id)
    if order is None:
        return {"ok": True, "found": False, "message": f"No order found with id {order_id}"}

    return {"ok": True, "found": True, "order": order}


def search_reviews(seller_id: str) -> dict:
    if not isinstance(seller_id, str) or not seller_id.strip():
        return {"ok": False, "error": "invalid_argument", "message": "seller_id must be a non-empty string"}

    seller_id = seller_id.strip().upper()

    if seller_id not in SELLERS:
        return {"ok": True, "found": False, "message": f"No seller found with id {seller_id}"}

    reviews = REVIEWS.get(seller_id, [])
    return {"ok": True, "found": True, "seller_id": seller_id, "review_count": len(reviews), "reviews": reviews}


def get_seller_info(seller_id: str) -> dict:
    if not isinstance(seller_id, str) or not seller_id.strip():
        return {"ok": False, "error": "invalid_argument", "message": "seller_id must be a non-empty string"}

    seller_id = seller_id.strip().upper()
    seller = SELLERS.get(seller_id)
    if seller is None:
        return {"ok": True, "found": False, "message": f"No seller found with id {seller_id}"}

    return {"ok": True, "found": True, "seller": seller}


# Registry the agent loop dispatches through. Keeping this separate from
# the Anthropic tool-schema definitions (in agent.py) means the schema
# and the implementation can be reviewed independently.
TOOL_REGISTRY = {
    "lookup_order": lookup_order,
    "search_reviews": search_reviews,
    "get_seller_info": get_seller_info,
}
