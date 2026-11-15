"""
SQLite Database module for Avito AI Monitor
Tracks seen listings, deal scores, price drops, and notification history.
"""

import sqlite3
import json
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avito_monitor.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH):
    """Initializes tables and indexes."""
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                item_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                price INTEGER,
                url TEXT NOT NULL,
                location TEXT,
                image_url TEXT,
                raw_description TEXT,
                ram_type TEXT,
                capacity_gb INTEGER,
                is_kit INTEGER DEFAULT 0,
                form_factor TEXT,
                frequency_mhz INTEGER,
                is_deal INTEGER DEFAULT 0,
                deal_rating TEXT,
                estimated_market_price INTEGER,
                ai_summary TEXT,
                red_flags TEXT,
                notified INTEGER DEFAULT 0,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                old_price INTEGER,
                new_price INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES listings (item_id)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_is_deal ON listings(is_deal)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_notified ON listings(notified)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen_at)")
        conn.commit()
    logger.info("Database initialized successfully at %s", db_path)


def is_item_seen(item_id: str, db_path: str = DB_PATH) -> bool:
    """Checks if an item has already been scraped and analyzed."""
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT 1 FROM listings WHERE item_id = ?", (str(item_id),))
        return cur.fetchone() is not None


def get_item(item_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves an existing item."""
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT * FROM listings WHERE item_id = ?", (str(item_id),))
        row = cur.fetchone()
        return dict(row) if row else None


def save_listing(item: Dict[str, Any], db_path: str = DB_PATH):
    """Saves or updates a listing and records price changes."""
    item_id = str(item["item_id"])
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT price FROM listings WHERE item_id = ?", (item_id,))
        existing = cur.fetchone()
        
        red_flags_val = item.get("red_flags")
        if isinstance(red_flags_val, list):
            red_flags_val = json.dumps(red_flags_val, ensure_ascii=False)

        now = datetime.utcnow().isoformat()
        if existing:
            old_price = existing["price"]
            new_price = item.get("price")
            if old_price is not None and new_price is not None and old_price != new_price:
                conn.execute(
                    "INSERT INTO price_history (item_id, old_price, new_price, recorded_at) VALUES (?, ?, ?, ?)",
                    (item_id, old_price, new_price, now)
                )
            conn.execute("""
                UPDATE listings SET
                    price = ?,
                    last_updated_at = ?,
                    is_deal = COALESCE(?, is_deal),
                    deal_rating = COALESCE(?, deal_rating),
                    ai_summary = COALESCE(?, ai_summary),
                    red_flags = COALESCE(?, red_flags)
                WHERE item_id = ?
            """, (
                new_price,
                now,
                1 if item.get("is_deal") else 0,
                item.get("deal_rating"),
                item.get("ai_summary"),
                red_flags_val,
                item_id
            ))
        else:
            conn.execute("""
                INSERT INTO listings (
                    item_id, title, price, url, location, image_url,
                    raw_description, ram_type, capacity_gb, is_kit,
                    form_factor, frequency_mhz, is_deal, deal_rating,
                    estimated_market_price, ai_summary, red_flags,
                    notified, first_seen_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                item.get("title", ""),
                item.get("price"),
                item.get("url", ""),
                item.get("location", ""),
                item.get("image_url", ""),
                item.get("raw_description", ""),
                item.get("ram_type"),
                item.get("capacity_gb"),
                1 if item.get("is_kit") else 0,
                item.get("form_factor"),
                item.get("frequency_mhz"),
                1 if item.get("is_deal") else 0,
                item.get("deal_rating"),
                item.get("estimated_market_price"),
                item.get("ai_summary"),
                red_flags_val,
                1 if item.get("notified") else 0,
                now,
                now
            ))
        conn.commit()


def mark_notified(item_id: str, db_path: str = DB_PATH):
    """Marks a deal listing as notified to the user."""
    with get_connection(db_path) as conn:
        conn.execute("UPDATE listings SET notified = 1 WHERE item_id = ?", (str(item_id),))
        conn.commit()


def get_stats(db_path: str = DB_PATH) -> Dict[str, int]:
    """Returns general database statistics."""
    with get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        deals = conn.execute("SELECT COUNT(*) FROM listings WHERE is_deal = 1").fetchone()[0]
        notified = conn.execute("SELECT COUNT(*) FROM listings WHERE notified = 1").fetchone()[0]
        return {
            "total_seen": total,
            "total_deals": deals,
            "total_notified": notified
        }


def init_verified_table(db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verified_deals (
                item_id TEXT PRIMARY KEY,
                query TEXT DEFAULT '',
                title TEXT NOT NULL,
                price INTEGER NOT NULL,
                url TEXT NOT NULL,
                location TEXT,
                specs TEXT DEFAULT '',
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        try:
            conn.execute("ALTER TABLE verified_deals ADD COLUMN query TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE verified_deals ADD COLUMN specs TEXT DEFAULT ''")
        except Exception:
            pass
        conn.commit()


def save_verified_deal(item: Dict[str, Any], query: str = "", db_path: str = DB_PATH):
    init_verified_table(db_path)
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO verified_deals (item_id, query, title, price, url, location, specs, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(item_id) DO UPDATE SET
                price = excluded.price,
                query = excluded.query,
                is_active = 1,
                verified_at = CURRENT_TIMESTAMP
        """, (
            str(item["item_id"]),
            query.strip().lower(),
            item.get("title", ""),
            item.get("price", 0),
            item.get("url", ""),
            item.get("location", ""),
            item.get("specs", "")
        ))
        conn.commit()


def mark_deal_reserved_or_inactive(item_id: str, db_path: str = DB_PATH):
    init_verified_table(db_path)
    with get_connection(db_path) as conn:
        conn.execute("UPDATE verified_deals SET is_active = 0 WHERE item_id = ?", (str(item_id),))
        conn.commit()


def get_all_time_top_deals(query: Optional[str] = None, limit: int = 5, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    init_verified_table(db_path)
    with get_connection(db_path) as conn:
        if query and query.strip():
            q_clean = query.strip().lower()
            rows = conn.execute("""
                SELECT item_id, query, title, price, url, location, specs, verified_at
                FROM verified_deals
                WHERE is_active = 1 AND query = ?
                ORDER BY price ASC
                LIMIT ?
            """, (q_clean, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT item_id, query, title, price, url, location, specs, verified_at
                FROM verified_deals
                WHERE is_active = 1
                ORDER BY price ASC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
