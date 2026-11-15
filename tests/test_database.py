"""
Tests for database module: connection lifecycle, idempotent migrations, and deal persistence.
Validates Tier 1 and 2 specifications.
Compatible with pytest and unittest.
"""

import os
import sqlite3
import tempfile
import unittest

from database import (
    get_connection,
    init_db,
    save_listing,
    get_item,
    save_verified_deal,
    get_all_time_top_deals,
    mark_deal_reserved_or_inactive,
    is_item_seen,
    get_stats,
    mark_notified,
)


class TestDatabaseConnectionLifecycle(unittest.TestCase):
    """Tier 1: Connection safety and guaranteed closing upon context exit."""

    def setUp(self):
        self.fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        init_db(self.db_path)

    def tearDown(self):
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def test_connection_closed_after_normal_exit(self):
        """Connection must be closed immediately upon normal exit from the with block."""
        captured_conn = None
        with get_connection(self.db_path) as conn:
            captured_conn = conn
            row = conn.execute("SELECT 1 as val").fetchone()
            self.assertEqual(row["val"], 1)

        # Outside the with block, executing queries must fail with ProgrammingError
        self.assertIsNotNone(captured_conn)
        with self.assertRaises(sqlite3.ProgrammingError) as cm:
            captured_conn.execute("SELECT 1")
        self.assertIn("closed", str(cm.exception).lower())

    def test_connection_closed_after_exception(self):
        """Connection must be closed even if an exception occurs inside the with block."""
        captured_conn = None
        try:
            with get_connection(self.db_path) as conn:
                captured_conn = conn
                raise ValueError("Forced error inside transaction block")
        except ValueError:
            pass

        self.assertIsNotNone(captured_conn)
        with self.assertRaises(sqlite3.ProgrammingError) as cm:
            captured_conn.execute("SELECT 1")
        self.assertIn("closed", str(cm.exception).lower())


class TestDatabaseSchemaAndIdempotentMigrations(unittest.TestCase):
    """Tier 1 & 2: Schema initialization, idempotent migration, columns, and indexes."""

    def setUp(self):
        self.fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)

    def tearDown(self):
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def test_idempotent_init_db_multiple_calls(self):
        """Calling init_db multiple times must succeed without error and preserve data."""
        # 1st call: fresh db
        init_db(self.db_path)
        # 2nd call: existing tables
        init_db(self.db_path)
        # 3rd call
        init_db(self.db_path)

        with get_connection(self.db_path) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            self.assertIn("listings", tables)
            self.assertIn("price_history", tables)
            self.assertIn("verified_deals", tables)

    def test_verified_deals_columns_exist(self):
        """Table verified_deals must contain query, specs, and is_active columns."""
        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(verified_deals)").fetchall()]
            self.assertIn("item_id", cols)
            self.assertIn("query", cols)
            self.assertIn("title", cols)
            self.assertIn("price", cols)
            self.assertIn("url", cols)
            self.assertIn("location", cols)
            self.assertIn("specs", cols)
            self.assertIn("verified_at", cols)
            self.assertIn("is_active", cols)

    def test_composite_indexes_exist(self):
        """Check composite index idx_verified_deals_active_query exists."""
        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            indexes = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]
            self.assertIn("idx_verified_deals_active_query", indexes)
            self.assertIn("idx_listings_is_deal", indexes)
            self.assertIn("idx_listings_notified", indexes)

    def test_legacy_database_migration(self):
        """Simulate a legacy DB without query and specs columns, verify init_db adds them."""
        with sqlite3.connect(self.db_path) as raw_conn:
            raw_conn.execute("""
                CREATE TABLE verified_deals (
                    item_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    location TEXT,
                    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            raw_conn.commit()

        # Run init_db migration
        init_db(self.db_path)

        with get_connection(self.db_path) as conn:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(verified_deals)").fetchall()]
            self.assertIn("query", cols)
            self.assertIn("specs", cols)
            self.assertIn("is_active", cols)


class TestDatabaseDealPersistenceOperations(unittest.TestCase):
    """Tier 2: Saving deals, querying active top deals, and marking reserved/inactive."""

    def setUp(self):
        self.fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        init_db(self.db_path)

    def tearDown(self):
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def test_save_and_retrieve_verified_deals(self):
        deal_1 = {
            "item_id": "vd_1001",
            "query": "rtx 3070",
            "title": "Nvidia RTX 3070 Founders Edition",
            "price": 25000,
            "url": "https://avito.ru/item/1001",
            "location": "Москва",
            "specs": "8GB GDDR6, 220W",
        }
        deal_2 = {
            "item_id": "vd_1002",
            "query": "rtx 3070",
            "title": "ASUS TUF RTX 3070 OC",
            "price": 27000,
            "url": "https://avito.ru/item/1002",
            "location": "Санкт-Петербург",
            "specs": "8GB GDDR6, Triple Fan",
        }

        save_verified_deal(deal_1, query="rtx 3070", db_path=self.db_path)
        save_verified_deal(deal_2, query="rtx 3070", db_path=self.db_path)

        deals = get_all_time_top_deals(query="rtx 3070", limit=10, db_path=self.db_path)
        self.assertEqual(len(deals), 2)
        # Price ASC
        self.assertEqual(deals[0]["item_id"], "vd_1001")
        self.assertEqual(deals[0]["price"], 25000)
        self.assertEqual(deals[1]["item_id"], "vd_1002")

    def test_mark_deal_reserved_or_inactive(self):
        deal = {
            "item_id": "vd_2001",
            "query": "rx 6700",
            "title": "PowerColor RX 6700 XT",
            "price": 22000,
            "url": "https://avito.ru/item/2001",
            "location": "Казань",
            "specs": "12GB GDDR6",
        }
        save_verified_deal(deal, query="rx 6700", db_path=self.db_path)

        # Before marking inactive
        active_deals = get_all_time_top_deals(query="rx 6700", db_path=self.db_path)
        self.assertEqual(len(active_deals), 1)

        # Mark inactive/reserved
        mark_deal_reserved_or_inactive("vd_2001", db_path=self.db_path)

        # After marking inactive: get_all_time_top_deals filters by is_active = 1
        active_deals_after = get_all_time_top_deals(query="rx 6700", db_path=self.db_path)
        self.assertEqual(len(active_deals_after), 0)

    def test_listing_and_price_history_operations(self):
        listing_data = {
            "item_id": "list_3001",
            "title": "Corsair DDR4 16GB 3200MHz",
            "price": 3500,
            "url": "https://avito.ru/item/3001",
            "location": "Новосибирск",
            "ram_type": "DDR4",
            "capacity_gb": 16,
            "is_kit": 1,
            "frequency_mhz": 3200,
            "is_deal": 1,
            "deal_rating": "HOT",
        }
        save_listing(listing_data, db_path=self.db_path)

        retrieved = get_item("list_3001", db_path=self.db_path)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["title"], listing_data["title"])
        self.assertEqual(retrieved["price"], 3500)
        self.assertTrue(is_item_seen("list_3001", db_path=self.db_path))

        # Price update triggers price_history recording
        updated_data = dict(listing_data)
        updated_data["price"] = 3000
        save_listing(updated_data, db_path=self.db_path)

        with get_connection(self.db_path) as conn:
            history = conn.execute("SELECT * FROM price_history WHERE item_id = ?", ("list_3001",)).fetchall()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["old_price"], 3500)
            self.assertEqual(history[0]["new_price"], 3000)

        # Mark notified and check stats
        mark_notified("list_3001", db_path=self.db_path)
        stats = get_stats(db_path=self.db_path)
        self.assertEqual(stats["total_seen"], 1)
        self.assertEqual(stats["total_deals"], 1)
        self.assertEqual(stats["total_notified"], 1)


if __name__ == "__main__":
    unittest.main()
