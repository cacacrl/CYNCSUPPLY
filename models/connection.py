"""
Persistence layer for CyncSupply.

Backend is chosen at import time:
  USE_SUPABASE=1  → Postgres (Supabase)
  USE_SUPABASE=0  → local SQLite file

All feature modules call read_df() / exec_sql() / exec_many() and never
care which backend is active. Use '?' placeholders in your SQL — they are
auto-rewritten to '%s' for Postgres.

Compatible with SQLAlchemy 2.x.
"""

import os
import hashlib
import hmac
import base64
from contextlib import contextmanager
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ==========================================
# BACKEND SELECTION
# ==========================================
USE_SUPABASE    = os.getenv("USE_SUPABASE", "0") == "1"
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "").strip()
SQLITE_PATH     = os.getenv("SQLITE_PATH", "cyncsupply.db")


def _build_engine():
    if USE_SUPABASE:
        if not SUPABASE_DB_URL:
            raise RuntimeError(
                "USE_SUPABASE=1 but SUPABASE_DB_URL is not set. "
                "Copy .env.example to .env and fill in the connection string."
            )
        return create_engine(
            SUPABASE_DB_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=1800,
        )

    return create_engine(
        f"sqlite:///{SQLITE_PATH}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )


engine = _build_engine()


def _adapt(sql: str) -> str:
    """Rewrite '?' placeholders to '%s' for Postgres."""
    if USE_SUPABASE:
        return sql.replace("?", "%s")
    return sql


@contextmanager
def get_conn():
    with engine.begin() as conn:
        yield conn


# ==========================================
# CORE QUERY HELPERS (SQLAlchemy 2.x safe)
# ==========================================
def read_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. Works with tuple params on SA 2.x."""
    with engine.connect() as conn:
        result = conn.exec_driver_sql(_adapt(sql), params)
        if result.returns_rows:
            rows = result.fetchall()
            cols = list(result.keys())
            return pd.DataFrame(rows, columns=cols)
        return pd.DataFrame()


def exec_sql(sql: str, params: tuple = ()) -> None:
    """Run an INSERT / UPDATE / DELETE with tuple params."""
    with engine.begin() as conn:
        conn.exec_driver_sql(_adapt(sql), params)


def exec_many(sql: str, seq) -> None:
    """Batch insert with a list of tuples."""
    with engine.begin() as conn:
        conn.exec_driver_sql(_adapt(sql), list(seq))


def backend_label() -> str:
    return "Supabase (Postgres)" if USE_SUPABASE else f"SQLite ({SQLITE_PATH})"


def health_check() -> tuple[bool, str]:
    """Returns (ok, message). Called at boot to display status."""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True, backend_label()
    except Exception as e:
        return False, f"{backend_label()} — {type(e).__name__}: {e}"


# ==========================================
# PASSWORD HASHING (PBKDF2-HMAC-SHA256, 200k iters)
# ==========================================
def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, hash_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return hmac.compare_digest(base64.b64encode(dk).decode(), hash_b64)


# ==========================================
# TIME HELPERS
# ==========================================
def now_ph() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Manila"))
    except Exception:
        return datetime.now()


def today_str() -> str:
    return now_ph().strftime("%Y-%m-%d")


def now_str() -> str:
    return now_ph().strftime("%Y-%m-%d %H:%M:%S")


# ==========================================
# SCHEMA
# ==========================================
def init_db() -> None:
    """Create tables. On Supabase this is a no-op — run supabase_schema.sql once."""
    if USE_SUPABASE:
        return

    with get_conn() as c:
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            name     TEXT NOT NULL,
            password TEXT NOT NULL,
            role     TEXT NOT NULL
        );
        """)
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS inventory (
            item_id        TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            category       TEXT NOT NULL,
            quantity       INTEGER NOT NULL DEFAULT 0,
            threshold      INTEGER NOT NULL DEFAULT 0,
            supplier_price REAL NOT NULL DEFAULT 0,
            supplier       TEXT NOT NULL DEFAULT ''
        );
        """)
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS sales (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT NOT NULL,
            item_id      TEXT,
            item_name    TEXT NOT NULL,
            units        INTEGER NOT NULL,
            category     TEXT NOT NULL,
            performed_by TEXT
        );
        """)
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_number     TEXT PRIMARY KEY,
            supplier      TEXT NOT NULL,
            total         REAL NOT NULL,
            status        TEXT NOT NULL,
            date          TEXT NOT NULL,
            dispatched_by TEXT
        );
        """)
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS po_line_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number  TEXT NOT NULL,
            item_name  TEXT NOT NULL,
            quantity   INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL
        );
        """)
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS pending_deliveries (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT,
            supplier  TEXT,
            item_name TEXT NOT NULL,
            ordered   INTEGER NOT NULL,
            eta       TEXT,
            added_by  TEXT
        );
        """)
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS receiving_tags (
            tag_id     TEXT PRIMARY KEY,
            item_name  TEXT NOT NULL,
            quantity   INTEGER NOT NULL,
            inspector  TEXT,
            supplier   TEXT,
            timestamp  TEXT NOT NULL,
            ref_note   TEXT
        );
        """)
        c.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS intake_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number    TEXT,
            supplier     TEXT,
            item_name    TEXT NOT NULL,
            ordered      INTEGER,
            verified_qty INTEGER NOT NULL,
            notes        TEXT,
            received     TEXT NOT NULL,
            received_by  TEXT
        );
        """)


# ==========================================
# SEED DATA
# ==========================================
SEED_INVENTORY = [
    ("CMT-001", "Holcim Portland Cement (40kg)",          "Cements",       150, 40, 235.00,  "Holcim Direct Phil"),
    ("CMT-002", "Pacific Pozzolan Cement (40kg)",         "Cements",        25, 35, 220.00,  "Pacific Cement Corp"),
    ("RBR-001", "9mm Grade 33 Deformed Rebar",            "Rebars",        300, 50, 165.00,  "Apex Steel Works"),
    ("RBR-002", "12mm Grade 40 Deformed Rebar",           "Rebars",         18, 30, 280.00,  "Apex Steel Works"),
    ("PNT-001", "Boysen Quick Drying Enamel White (4L)",  "Paints",         45, 15, 680.00,  "Pacific Paint Inc"),
    ("PNT-002", "Davies Megacryl Latex Flat Black (4L)",  "Paints",          8, 12, 620.00,  "Davies Paints Phil"),
    ("SND-001", "Coarse Washing Sand (per cu.m)",         "Sand & Gravel",  60, 20, 950.00,  "Davao Quarry Supplies"),
    ("SND-002", "Fine Screening Sand (per cu.m)",         "Sand & Gravel",  12, 15, 1050.00, "Davao Quarry Supplies"),
]

SEED_USERS = [
    ("carlf", "Carlos Anay",   "password123", "Inventory Manager"),
    ("admin", "Administrator", "admin123",    "System Admin"),
    ("clerk", "Yard Clerk",    "clerk123",    "Yard Clerk / Inspector"),
    ("sales", "Sales Analyst", "sales123",    "Sales Analyst"),
]

SEED_SALES = [
    ("2026-09-24", "CMT-001", "Holcim Portland Cement (40kg)",         45, "Cements",       "Carlos Anay"),
    ("2026-09-25", "RBR-001", "9mm Grade 33 Deformed Rebar",           80, "Rebars",        "Carlos Anay"),
    ("2026-09-26", "PNT-001", "Boysen Quick Drying Enamel White (4L)", 15, "Paints",        "Carlos Anay"),
    ("2026-09-27", "SND-001", "Coarse Washing Sand (per cu.m)",        25, "Sand & Gravel", "Carlos Anay"),
    ("2026-09-28", "CMT-001", "Holcim Portland Cement (40kg)",         60, "Cements",       "Carlos Anay"),
    ("2026-09-29", "CMT-001", "Holcim Portland Cement (40kg)",         55, "Cements",       "Carlos Anay"),
    ("2026-09-29", "RBR-001", "9mm Grade 33 Deformed Rebar",           40, "Rebars",        "Carlos Anay"),
    ("2026-09-30", "PNT-002", "Davies Megacryl Latex Flat Black (4L)", 22, "Paints",        "Carlos Anay"),
    ("2026-10-01", "SND-001", "Coarse Washing Sand (per cu.m)",        35, "Sand & Gravel", "Carlos Anay"),
    ("2026-10-01", "CMT-002", "Pacific Pozzolan Cement (40kg)",        30, "Cements",       "Carlos Anay"),
]


def seed_if_empty() -> None:
    """SQLite only. On Supabase, run supabase_schema.sql once."""
    if USE_SUPABASE:
        return

    with get_conn() as c:
        n = c.exec_driver_sql("SELECT COUNT(*) FROM users").scalar()
        if n == 0:
            c.exec_driver_sql(
                "INSERT INTO users (username, name, password, role) VALUES (?, ?, ?, ?)",
                [(u, nm, hash_password(p), r) for u, nm, p, r in SEED_USERS],
            )

        n = c.exec_driver_sql("SELECT COUNT(*) FROM inventory").scalar()
        if n == 0:
            c.exec_driver_sql(
                "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?)",
                SEED_INVENTORY,
            )

        n = c.exec_driver_sql("SELECT COUNT(*) FROM sales").scalar()
        if n == 0:
            c.exec_driver_sql(
                "INSERT INTO sales (date, item_id, item_name, units, category, performed_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                SEED_SALES,
            )


# ==========================================
# DOMAIN HELPERS
# ==========================================
def vendors_for_item(item_name: str) -> list[str]:
    """Vendor routing: primary supplier first, then alternates in same category."""
    df = read_df("SELECT supplier, category FROM inventory WHERE name = ?", (item_name,))
    if df.empty:
        return []
    primary = df.iloc[0]["supplier"]
    category = df.iloc[0]["category"]
    others = read_df(
        "SELECT DISTINCT supplier FROM inventory WHERE category = ? AND supplier <> ?",
        (category, primary),
    )["supplier"].tolist()
    return [primary] + others


def next_po_number() -> str:
    n = read_df("SELECT COUNT(*) AS n FROM purchase_orders").iloc[0]["n"]
    return f"PO-{today_str()[:7].replace('-', '')}-{int(n) + 1:04d}"


# ==========================================
# FLASH MESSAGES (used by feature modules)
# ==========================================
def flash(level: str, msg: str) -> None:
    """Queue a flash message to display on the next render pass."""
    import streamlit as st
    st.session_state.setdefault("_flash", []).append((level, msg))


def render_flashes() -> None:
    """Display and clear any queued flash messages."""
    import streamlit as st
    for level, msg in st.session_state.pop("_flash", []):
        getattr(st, level)(msg)