"""
auth_utils.py — Authentication Helpers
========================================
Provides:
  • password hashing with PBKDF2-SHA256 (Python stdlib — zero extra installs)
  • JWT token generation and verification
  • A @login_required decorator to protect routes

Why PBKDF2?
  Built into Python's hashlib. OWASP-approved at 600 000 iterations.
  Safer than plain SHA/MD5. No C extension required (unlike bcrypt).
"""

import jwt
import hashlib
import hmac
import os
import functools
from datetime import datetime, timedelta, timezone
from flask import request, jsonify, current_app


# ─────────────────────────────────────────────────────────────────
#  Password helpers  (PBKDF2-SHA256)
# ─────────────────────────────────────────────────────────────────

ITERATIONS = 600_000          # OWASP 2023 recommendation for PBKDF2-SHA256
HASH_ALG   = "sha256"


def hash_password(plain_text: str) -> str:
    """
    Hash a plain-text password using PBKDF2-SHA256.
    Generates a random 16-byte salt per password.

    Stored format:   <hex_salt>$<hex_hash>
    Both parts are stored together in one DB column.
    """
    salt   = os.urandom(16)                           # 16 random bytes
    dk     = hashlib.pbkdf2_hmac(
        HASH_ALG,
        plain_text.encode("utf-8"),
        salt,
        ITERATIONS,
    )
    return salt.hex() + "$" + dk.hex()


def check_password(plain_text: str, stored_hash: str) -> bool:
    """
    Verify a plain-text attempt against a stored PBKDF2 hash.
    Uses hmac.compare_digest to prevent timing attacks.
    Returns True on match, False otherwise.
    """
    try:
        salt_hex, hash_hex = stored_hash.split("$", 1)
    except ValueError:
        return False   # malformed stored hash

    salt   = bytes.fromhex(salt_hex)
    dk     = hashlib.pbkdf2_hmac(
        HASH_ALG,
        plain_text.encode("utf-8"),
        salt,
        ITERATIONS,
    )
    # Constant-time comparison prevents timing oracle attacks
    return hmac.compare_digest(dk.hex(), hash_hex)


# ─────────────────────────────────────────────────────────────────
#  JWT helpers
# ─────────────────────────────────────────────────────────────────

def generate_token(user_id: int, email: str) -> str:
    """
    Create a signed JWT the frontend stores in localStorage.

    Payload:
        user_id  — integer PK from the users table
        email    — user's email
        exp      — expiry: 7 days from now
        iat      — issued-at timestamp
    """
    expiry = datetime.now(timezone.utc) + timedelta(
        seconds=current_app.config["JWT_EXPIRY_SECONDS"]
    )
    payload = {
        "user_id": user_id,
        "email":   email,
        "exp":     expiry,
        "iat":     datetime.now(timezone.utc),
    }
    return jwt.encode(
        payload,
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def decode_token(token: str):
    """
    Decode and verify a JWT.
    Returns the payload dict on success, None on any failure.
    """
    try:
        return jwt.decode(
            token,
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        return None    # token has expired
    except jwt.InvalidTokenError:
        return None    # tampered or malformed


# ─────────────────────────────────────────────────────────────────
#  Route decorator
# ─────────────────────────────────────────────────────────────────

def login_required(f):
    """
    Protects a route — the caller must send:
        Authorization: Bearer <jwt_token>

    On success the decoded payload is injected as the keyword
    argument `current_user` into the route function.

    Example usage:
        @orders_bp.route('/my-orders')
        @login_required
        def my_orders(current_user):
            uid = current_user['user_id']
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or malformed token"}), 401

        token   = auth_header.split(" ", 1)[1]
        payload = decode_token(token)

        if payload is None:
            return jsonify({"error": "Token is invalid or expired. Please log in again."}), 401

        kwargs["current_user"] = payload
        return f(*args, **kwargs)

    return wrapper
