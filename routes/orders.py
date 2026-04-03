"""
routes/orders.py — Orders Routes
==================================
Endpoints:
  POST /api/orders/place          → Place a new order (login required)
  GET  /api/orders/my-orders      → List all orders for logged-in user
  GET  /api/orders/<order_id>     → Get details of one order
  PUT  /api/orders/<order_id>/step → Advance order tracking step (simulate delivery)
  DELETE /api/orders/<order_id>   → Cancel a pending order

All protected endpoints require: Authorization: Bearer <token>
"""

import json
import random
import string
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from database   import fetch_one, fetch_all, execute
from auth_utils import login_required

orders_bp = Blueprint("orders", __name__)


# ─────────────────────────────────────────────────────────────────
#  Helper: generate a unique order ID like "RE-2024-A3BX"
# ─────────────────────────────────────────────────────────────────
def generate_order_id():
    year  = datetime.now().year
    chars = string.ascii_uppercase + string.digits
    rand  = "".join(random.choices(chars, k=8))
    return f"RE-{year}-{rand}"


# ─────────────────────────────────────────────────────────────────
#  POST /api/orders/place
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/place", methods=["POST"])
@login_required
def place_order(current_user):
    """
    Place a new order.

    Expected JSON body:
        {
            "items": [
                { "id": 1, "name": "Butter Chicken", "price": 320,
                  "qty": 2, "restaurant": "Tandoor House", "emoji": "🍗" }
            ],
            "address": "Flat 4B, MG Road, Mumbai",
            "payment_method": "upi"
        }

    Returns:
        201  { "message": "...", "order": { ... } }
        400  { "error": "..." }
    """
    data = request.get_json()

    items          = data.get("items", [])
    address        = data.get("address", "").strip()
    payment_method = data.get("payment_method", "cod")

    # ── Validate ────────────────────────────────────────────────
    if not items:
        return jsonify({"error": "Cart is empty — add items before placing an order"}), 400
    if not address:
        return jsonify({"error": "Delivery address is required"}), 400

    # ── Calculate totals ─────────────────────────────────────────
    subtotal = sum(i.get("price", 0) * i.get("qty", 1) for i in items)
    delivery = 0 if subtotal >= 500 else 49
    taxes    = round(subtotal * 0.05)
    total    = subtotal + delivery + taxes

    # ── Build the order row ───────────────────────────────────────
    order_id   = generate_order_id()
    restaurant = items[0].get("restaurant", "") if items else ""

    # Store items as a JSON string (SQLite has no array type)
    items_json = json.dumps(items)

    execute(
        """INSERT INTO orders
           (id, user_id, items, total, restaurant, address, status, current_step)
           VALUES (?, ?, ?, ?, ?, ?, 'placed', 0)""",
        (order_id, current_user["user_id"], items_json, total, restaurant, address),
    )

    # ── Return the created order to the frontend ──────────────────
    now      = datetime.now(timezone.utc)
    time_str = now.strftime("%I:%M %p")

    return jsonify({
        "message": f"Order {order_id} placed successfully! 🎉",
        "order": {
            "id":           order_id,
            "status":       "placed",
            "current_step": 0,
            "eta":          "30 mins",
            "items":        [i.get("name", "") for i in items],
            "restaurant":   restaurant,
            "time":         time_str,
            "total":        total,
            "subtotal":     subtotal,
            "delivery":     delivery,
            "taxes":        taxes,
            "address":      address,
            "placed_at":    now.isoformat(),
            "payment_method": payment_method,
        },
    }), 201


# ─────────────────────────────────────────────────────────────────
#  GET /api/orders/my-orders
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/my-orders", methods=["GET"])
@login_required
def my_orders(current_user):
    """Return all orders placed by the logged-in user (newest first)."""
    rows = fetch_all(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY placed_at DESC",
        (current_user["user_id"],),
    )

    # Parse stored JSON items back to list
    for row in rows:
        try:
            row["items"] = json.loads(row["items"])
        except Exception:
            row["items"] = []

    return jsonify({"orders": rows, "count": len(rows)}), 200


# ─────────────────────────────────────────────────────────────────
#  GET /api/orders/<order_id>
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/<order_id>", methods=["GET"])
@login_required
def get_order(order_id, current_user):
    """Get full details of a single order (must belong to current user)."""
    order = fetch_one(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, current_user["user_id"]),
    )
    if not order:
        return jsonify({"error": "Order not found"}), 404

    try:
        order["items"] = json.loads(order["items"])
    except Exception:
        order["items"] = []

    return jsonify({"order": order}), 200


# ─────────────────────────────────────────────────────────────────
#  PUT /api/orders/<order_id>/step
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/<order_id>/step", methods=["PUT"])
@login_required
def advance_step(order_id, current_user):
    """
    Advance the tracking step of an order by 1.
    Steps: 0=placed → 1=preparing → 2=on_the_way → 3=nearby → 4=delivered

    Used by the frontend to simulate delivery progression.
    In a real app this would be triggered by the delivery partner's app.
    """
    STATUS_MAP = {
        0: "placed",
        1: "preparing",
        2: "on_the_way",
        3: "nearby",
        4: "delivered",
    }

    order = fetch_one(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, current_user["user_id"]),
    )
    if not order:
        return jsonify({"error": "Order not found"}), 404

    current_step = order["current_step"] or 0

    if current_step >= 4:
        return jsonify({"message": "Order already delivered", "current_step": 4}), 200

    next_step   = current_step + 1
    next_status = STATUS_MAP[next_step]

    execute(
        "UPDATE orders SET current_step = ?, status = ? WHERE id = ?",
        (next_step, next_status, order_id),
    )

    return jsonify({
        "message":      f"Order is now: {next_status.replace('_', ' ').title()}",
        "current_step": next_step,
        "status":       next_status,
    }), 200


# ─────────────────────────────────────────────────────────────────
#  DELETE /api/orders/<order_id>
# ─────────────────────────────────────────────────────────────────
@orders_bp.route("/<order_id>", methods=["DELETE"])
@login_required
def cancel_order(order_id, current_user):
    """Cancel an order — only allowed if status is 'placed' (not yet preparing)."""
    order = fetch_one(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, current_user["user_id"]),
    )
    if not order:
        return jsonify({"error": "Order not found"}), 404

    if order["status"] != "placed":
        return jsonify({
            "error": "Cannot cancel — your order is already being prepared",
        }), 400

    execute("DELETE FROM orders WHERE id = ?", (order_id,))
    return jsonify({"message": f"Order {order_id} cancelled successfully"}), 200
