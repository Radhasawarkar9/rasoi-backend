"""
database.py — Supabase (PostgreSQL) Database Layer
=====================================================
Drop-in replacement for the original SQLite database.py.

Same public interface:
  fetch_one(sql, params) -> dict | None
  fetch_all(sql, params) -> list[dict]
  execute(sql, params)   -> last inserted id | None

Key changes from SQLite version:
  - Uses psycopg2 to connect to Supabase's PostgreSQL
  - Auto-converts SQLite ? placeholders to psycopg2 %s style
  - AUTOINCREMENT -> SERIAL, DATETIME -> TIMESTAMP
  - Connection URL read from SUPABASE_DB_URL environment variable
"""

import re
import os
import psycopg2
import psycopg2.extras
from flask import g, current_app


# ─────────────────────────────────────────────────────────────────
#  Schema (PostgreSQL-compatible)
# ─────────────────────────────────────────────────────────────────

SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        name          TEXT    NOT NULL,
        email         TEXT    NOT NULL UNIQUE,
        password      TEXT    NOT NULL,
        phone         TEXT    DEFAULT '',
        address       TEXT    DEFAULT '',
        picture       TEXT    DEFAULT '',
        profile_color TEXT    DEFAULT '#1A6FB3',
        created_at    TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS menu_items (
        id          SERIAL PRIMARY KEY,
        name        TEXT    NOT NULL,
        description TEXT    DEFAULT '',
        price       FLOAT   NOT NULL,
        category    TEXT    NOT NULL,
        type        TEXT    DEFAULT 'veg',
        restaurant  TEXT    DEFAULT '',
        rating      FLOAT   DEFAULT 4.0,
        image       TEXT    DEFAULT '',
        emoji       TEXT    DEFAULT '🍛',
        is_spicy    INTEGER DEFAULT 0,
        is_new      INTEGER DEFAULT 0,
        is_best     INTEGER DEFAULT 0,
        time        TEXT    DEFAULT '30 mins',
        available   INTEGER DEFAULT 1,
        created_at  TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS orders (
        id           TEXT    PRIMARY KEY,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        items        TEXT    NOT NULL,
        total        FLOAT   NOT NULL,
        restaurant   TEXT    DEFAULT '',
        address      TEXT    DEFAULT '',
        status       TEXT    DEFAULT 'placed',
        current_step INTEGER DEFAULT 0,
        placed_at    TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS cart_items (
        id      SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        dish_id INTEGER NOT NULL REFERENCES menu_items(id),
        qty     INTEGER NOT NULL DEFAULT 1,
        UNIQUE(user_id, dish_id)
    )""",
]


def _to_pg(sql: str) -> str:
    """Convert SQLite ? placeholders to psycopg2 %s style."""
    return re.sub(r'\?', '%s', sql)


def init_db(app):
    """Called once at startup — creates tables if they don't exist."""
    with app.app_context():
        conn = psycopg2.connect(app.config["SUPABASE_DB_URL"])
        cur = conn.cursor()
        for stmt in SCHEMA_STATEMENTS:
            cur.execute(stmt)
        conn.commit()
        cur.close()
        conn.close()
        print("✅  Supabase database ready")


def get_db():
    """Returns a psycopg2 connection for the current request (stored on g)."""
    if "db" not in g:
        g.db = psycopg2.connect(
            current_app.config["SUPABASE_DB_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return g.db


def close_db(e=None):
    """Closes the DB connection at the end of a request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def fetch_one(sql: str, params=()):
    """Run a SELECT returning a single row dict, or None."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_to_pg(sql), params)
    row = cur.fetchone()
    cur.close()
    return dict(row) if row else None


def fetch_all(sql: str, params=()):
    """Run a SELECT returning all rows as list of dicts."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_to_pg(sql), params)
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]


def execute(sql: str, params=()):
    """
    Run INSERT / UPDATE / DELETE and commit.
    Returns the new row's id for INSERTs (via RETURNING id), else None.
    """
    conn = get_db()
    cur = conn.cursor()
    pg_sql = _to_pg(sql)

    is_insert = pg_sql.strip().upper().startswith("INSERT")
    if is_insert and "RETURNING" not in pg_sql.upper():
        pg_sql += " RETURNING id"

    cur.execute(pg_sql, params)
    conn.commit()

    last_id = None
    if is_insert:
        row = cur.fetchone()
        if row:
            last_id = row["id"] if isinstance(row, dict) else row[0]

    cur.close()
    return last_id
