"""
routes/auth.py — Authentication Routes
=========================================
Endpoints:
  POST /api/auth/signup   → Register a new user
  POST /api/auth/login    → Log in, get JWT token
  GET  /api/auth/me       → Get currently logged-in user's profile
  POST /api/auth/logout   → Invalidate session (client-side — token is discarded)

All responses are JSON. Passwords are NEVER stored or returned in plain text.
"""

from flask import Blueprint, request, jsonify
from database  import fetch_one, execute
from auth_utils import hash_password, check_password, generate_token, login_required

# ── Blueprint — all routes here are prefixed with /api/auth ─────
auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────────────────────────
#  POST /api/auth/signup
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/signup", methods=["POST"])
def signup():
    """
    Register a new user account.

    Expected JSON body:
        { "name": "Priya Sharma", "email": "priya@example.com", "password": "secret123" }

    Returns:
        201  { "message": "Account created!", "token": "...", "user": {...} }
        400  { "error": "..." }   — validation or duplicate email
    """
    data = request.get_json()

    # ── 1. Validate required fields ──────────────────────────────
    name     = (data.get("name")     or "").strip()
    email    = (data.get("email")    or "").strip().lower()
    password = (data.get("password") or "")

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "A valid email address is required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # ── 2. Check if email is already registered ──────────────────
    existing = fetch_one("SELECT id FROM users WHERE email = ?", (email,))
    if existing:
        return jsonify({"error": "This email is already registered. Please log in."}), 400

    # ── 3. Hash the password and save the user ───────────────────
    hashed_pw = hash_password(password)
    user_id   = execute(
        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
        (name, email, hashed_pw),
    )

    # ── 4. Generate a JWT token so the user is logged in right away
    token = generate_token(user_id, email)

    # ── 5. Return success ────────────────────────────────────────
    return jsonify({
        "message": f"Welcome to RasoiExpress, {name.split()[0]}! 🎉",
        "token":   token,
        "user": {
            "id":            user_id,
            "name":          name,
            "email":         email,
            "picture":       "",
            "profile_color": "#1A6FB3",
            "phone":         "",
            "address":       "",
        },
    }), 201


# ─────────────────────────────────────────────────────────────────
#  POST /api/auth/login
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Log in with email and password.

    Expected JSON body:
        { "email": "priya@example.com", "password": "secret123" }

    Returns:
        200  { "message": "Welcome back!", "token": "...", "user": {...} }
        400  { "error": "..." }  — missing fields
        401  { "error": "..." }  — wrong credentials
    """
    data = request.get_json()

    email    = (data.get("email")    or "").strip().lower()
    password = (data.get("password") or "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # ── Fetch user from DB ────────────────────────────────────────
    user = fetch_one(
        "SELECT id, name, email, password, phone, address, picture, profile_color "
        "FROM users WHERE email = ?",
        (email,),
    )

    # ── Intentionally vague error — don't reveal whether email exists
    if not user or not check_password(password, user["password"]):
        return jsonify({"error": "Invalid email or password"}), 401

    # ── Issue JWT ────────────────────────────────────────────────
    token = generate_token(user["id"], user["email"])

    first_name = user["name"].split()[0]
    return jsonify({
        "message": f"Welcome back, {first_name}! 🎉",
        "token":   token,
        "user": {
            "id":            user["id"],
            "name":          user["name"],
            "email":         user["email"],
            "picture":       user["picture"]       or "",
            "profile_color": user["profile_color"] or "#1A6FB3",
            "phone":         user["phone"]         or "",
            "address":       user["address"]       or "",
        },
    }), 200


# ─────────────────────────────────────────────────────────────────
#  GET /api/auth/me
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
@login_required
def me(current_user):
    """
    Return the logged-in user's profile.
    Requires: Authorization: Bearer <token>

    Useful for re-hydrating state when the page reloads.
    """
    user = fetch_one(
        "SELECT id, name, email, phone, address, picture, profile_color, created_at "
        "FROM users WHERE id = ?",
        (current_user["user_id"],),
    )
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Count their orders for profile stats
    order_count = fetch_one(
        "SELECT COUNT(*) as cnt FROM orders WHERE user_id = ?",
        (current_user["user_id"],),
    )

    user["total_orders"] = order_count["cnt"] if order_count else 0
    return jsonify({"user": user}), 200


# ─────────────────────────────────────────────────────────────────
#  POST /api/auth/logout
# ─────────────────────────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    Logout endpoint.
    JWTs are stateless — the real logout happens on the frontend by
    deleting the token from localStorage.  This endpoint just confirms.
    """
    return jsonify({"message": "Logged out successfully"}), 200
