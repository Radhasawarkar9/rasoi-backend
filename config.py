"""
config.py — Application Configuration
======================================
Supabase-integrated version. All secrets come from environment variables.

Required environment variables:
    SUPABASE_DB_URL  — PostgreSQL connection string from Supabase
                       Format: postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres
    SECRET_KEY       — JWT signing secret (use a long random string in production)

Optional:
    ADMIN_PASSWORD   — Admin panel password (default: secure@123)
    DEBUG            — Set to "false" in production
"""

import os


class Config:
    # ── Supabase PostgreSQL connection URL ───────────────────────
    # Get this from: Supabase Dashboard → Settings → Database → Connection string (URI)
    SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

    # ── Supabase project keys (used for reference / future SDK use) ─
    SUPABASE_URL    = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY    = os.environ.get("SUPABASE_KEY", "")

    # ── Secret key for signing JWT tokens ───────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "rasoi-express-secret-key-change-in-prod")

    # ── JWT token expiry (seconds) ───────────────────────────────
    JWT_EXPIRY_SECONDS = 60 * 60 * 24 * 7    # 7 days

    # ── Admin credentials ────────────────────────────────────────
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "secure@123")

    # ── Debug flag (always False in production) ──────────────────
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
