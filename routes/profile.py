"""
routes/profile.py — User Profile Routes
=========================================
Endpoints:
  GET  /api/profile           → Get full profile with order stats
  PUT  /api/profile           → Update name, phone, address, picture, color
  PUT  /api/profile/password  → Change password (requires current password)
  DELETE /api/profile         → Delete account permanently

All endpoints require: Authorization: Bearer <token>
"""

from flask import Blueprint, request, jsonify
from database   import fetch_one, fetch_all, execute
from auth_utils import login_required, hash_password, check_password

profile_bp = Blueprint("profile", __name__)


# ─────────────────────────────────────────────────────────────────
#  GET /api/profile
# ─────────────────────────────────────────────────────────────────
@profile_bp.route("", methods=["GET"])
@login_required
def get_profile(current_user):
    """
    Return full profile data including order statistics.
    The frontend uses this to display the profile page.
    """
    user = fetch_one(
        "SELECT id, name, email, phone, address, picture, profile_color, created_at "
        "FROM users WHERE id = ?",
        (current_user["user_id"],),
    )
    if not user:
        return jsonify({"error": "User not found"}), 404

    # ── Order statistics ─────────────────────────────────────────
    stats = fetch_one(
        "SELECT COUNT(*) as total_orders, COALESCE(SUM(total), 0) as total_spent "
        "FROM orders WHERE user_id = ?",
        (current_user["user_id"],),
    )

    user["total_orders"] = stats["total_orders"] if stats else 0
    user["total_spent"]  = round(stats["total_spent"], 2) if stats else 0.0

    return jsonify({"user": user}), 200


# ─────────────────────────────────────────────────────────────────
#  PUT /api/profile
# ─────────────────────────────────────────────────────────────────
@profile_bp.route("", methods=["PUT"])
@login_required
def update_profile(current_user):
    """
    Update the user's profile information.

    Accepted JSON fields (all optional — only provided fields are updated):
        name, phone, address, picture (URL or base64), profile_color

    Returns:
        200  { "message": "...", "user": { updated user object } }
    """
    data = request.get_json()

    # ── Fetch current values so we don't accidentally blank fields ─
    current = fetch_one(
        "SELECT name, phone, address, picture, profile_color FROM users WHERE id = ?",
        (current_user["user_id"],),
    )
    if not current:
        return jsonify({"error": "User not found"}), 404

    # ── Use provided values, fall back to existing values ────────
    name          = (data.get("name")          or current["name"]).strip()
    phone         = (data.get("phone")         or current["phone"]         or "").strip()
    address       = (data.get("address")       or current["address"]       or "").strip()
    picture       = (data.get("picture")       or current["picture"]       or "")
    profile_color = (data.get("profile_color") or current["profile_color"] or "#1A6FB3")

    if not name:
        return jsonify({"error": "Name cannot be empty"}), 400

    execute(
        """UPDATE users
           SET name = ?, phone = ?, address = ?, picture = ?, profile_color = ?
           WHERE id = ?""",
        (name, phone, address, picture, profile_color, current_user["user_id"]),
    )

    # Return the updated user object
    updated = fetch_one(
        "SELECT id, name, email, phone, address, picture, profile_color FROM users WHERE id = ?",
        (current_user["user_id"],),
    )
    return jsonify({
        "message": "Profile updated successfully ✅",
        "user":    updated,
    }), 200


# ─────────────────────────────────────────────────────────────────
#  PUT /api/profile/password
# ─────────────────────────────────────────────────────────────────
@profile_bp.route("/password", methods=["PUT"])
@login_required
def change_password(current_user):
    """
    Change the user's password.

    Expected JSON body:
        { "current_password": "old123", "new_password": "new456" }

    Security note: we always verify the current password before allowing a change.
    """
    data = request.get_json()

    current_pw = data.get("current_password", "")
    new_pw     = data.get("new_password",     "")

    if not current_pw or not new_pw:
        return jsonify({"error": "Both current and new password are required"}), 400
    if len(new_pw) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400

    # ── Verify current password ───────────────────────────────────
    user = fetch_one(
        "SELECT password FROM users WHERE id = ?",
        (current_user["user_id"],),
    )
    if not user or not check_password(current_pw, user["password"]):
        return jsonify({"error": "Current password is incorrect"}), 401

    # ── Hash and store the new password ───────────────────────────
    new_hash = hash_password(new_pw)
    execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (new_hash, current_user["user_id"]),
    )

    return jsonify({"message": "Password changed successfully 🔒"}), 200


# ─────────────────────────────────────────────────────────────────
#  DELETE /api/profile
# ─────────────────────────────────────────────────────────────────
@profile_bp.route("", methods=["DELETE"])
@login_required
def delete_account(current_user):
    """
    Permanently delete the user account and all their orders.
    Requires password confirmation for safety.

    Expected JSON body:
        { "password": "their_password" }
    """
    data = request.get_json()
    password = data.get("password", "")

    if not password:
        return jsonify({"error": "Password is required to delete your account"}), 400

    user = fetch_one(
        "SELECT password FROM users WHERE id = ?",
        (current_user["user_id"],),
    )
    if not user or not check_password(password, user["password"]):
        return jsonify({"error": "Incorrect password"}), 401

    # ── Delete orders first (foreign key) ────────────────────────
    execute("DELETE FROM orders    WHERE user_id = ?", (current_user["user_id"],))
    execute("DELETE FROM cart_items WHERE user_id = ?", (current_user["user_id"],))
    execute("DELETE FROM users     WHERE id = ?",      (current_user["user_id"],))

    return jsonify({"message": "Account deleted. We'll miss you 😢"}), 200
