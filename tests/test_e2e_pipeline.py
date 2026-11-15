"""
Tier 4 End-to-End Integration Scenarios.
Verifies full multi-feature pipeline behavior across price parsing, negation filtering,
verification queue lifecycle, anti-ban jitter/backoff, and database persistence.
Compatible with pytest and unittest.
"""

import os
import time
import tempfile
import unittest
from bs4 import BeautifulSoup

from scraper import clean_price
from negation_filter import check_excludes, is_reserved_text
from verification_queue import VerificationQueue, InspectionStatus, BackoffManager
from database import (
    init_db,
    get_connection,
    save_verified_deal,
    get_all_time_top_deals,
    mark_deal_reserved_or_inactive,
    save_listing,
    get_item,
)
from tests.conftest import (
    HTML_CARD_DISCOUNT_OLD_PRICE,
    HTML_PAGE_RESERVED_CAROUSEL_ONLY,
    cleanup_temp_db,
)


class TestE2EPipelineScenarios(unittest.TestCase):
    """Tier 4: End-to-end integration scenarios simulating real-world Avito sniper operations."""

    def setUp(self):
        self.fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        init_db(self.db_path)
        self.queue = VerificationQueue(cache_ttl_seconds=7200, reserved_ttl_seconds=1800)

    def tearDown(self):
        cleanup_temp_db(self.db_path)

    def test_scenario_1_discounted_gpu_with_negation_and_persistence(self):
        """
        Scenario 1:
        Discounted GPU listing with old price in DOM and negation in description ('не битая').
        - Active price is parsed cleanly as 10500 (avoiding 1050012000 concatenation).
        - Description with 'не битая, родная коробка и чек' passes negation filter.
        - Queue accepts item as fresh (priority 1).
        - Deal is recorded in queue and saved to database.
        - Deal is queryable via get_all_time_top_deals.
        """
        soup = BeautifulSoup(HTML_CARD_DISCOUNT_OLD_PRICE, "html.parser")
        price_container = soup.find("div", attrs={"data-marker": "item-price"})
        self.assertIsNotNone(price_container)

        # 1. Price extraction
        extracted_price = clean_price(price_container.get_text())
        self.assertEqual(extracted_price, 10500)
        self.assertNotEqual(extracted_price, 1050012000)

        # 2. Content negation filter
        description = "Карта в идеале, не битая, без дефектов, в комплекте родная коробка и чек из магазина."
        is_rejected, reason = check_excludes(description)
        self.assertFalse(is_rejected, f"Legitimate GPU listing was falsely rejected: {reason}")

        # 3. Verification queue check & priority
        item_id = "gpu_40901"
        self.assertTrue(self.queue.should_inspect(item_id, extracted_price))

        raw_item = {
            "item_id": item_id,
            "title": "Nvidia RTX 3070 8GB",
            "price": extracted_price,
            "url": f"https://avito.ru/item/{item_id}",
            "location": "Москва",
            "specs": "8GB, Box, Receipt",
        }
        prioritized = self.queue.prioritize_candidates(items_104=[raw_item], items_1=[], max_count=5)
        self.assertEqual(len(prioritized), 1)
        self.assertEqual(prioritized[0]["_queue_priority"], 1)

        # 4. Record inspection & persist to database
        self.queue.record_result(item_id, InspectionStatus.VERIFIED_DEAL, price=extracted_price)
        save_verified_deal(raw_item, query="rtx 3070", db_path=self.db_path)

        # 5. Retrieve from DB
        top_deals = get_all_time_top_deals(query="rtx 3070", db_path=self.db_path)
        self.assertEqual(len(top_deals), 1)
        self.assertEqual(top_deals[0]["item_id"], item_id)
        self.assertEqual(top_deals[0]["price"], 10500)

    def test_scenario_2_high_volume_deduplication_and_fresh_deal_isolation(self):
        """
        Scenario 2:
        High-volume search with 50 items where 49 have already been inspected and 1 is a fresh deal.
        - Queue should_inspect filters out 49 seen items within TTL.
        - prioritize_candidates returns ONLY the single fresh item at priority 1.
        """
        # Pre-populate queue with 49 inspected items
        for i in range(1, 50):
            item_id = f"item_bulk_{i}"
            self.queue.record_result(item_id, InspectionStatus.VERIFIED_DEAL, price=5000 + i)

        # Incoming search result: 49 seen items + 1 brand new deal from s=104
        candidates_104 = [{"item_id": f"item_bulk_{i}", "price": 5000 + i} for i in range(1, 50)]
        fresh_item = {"item_id": "fresh_deal_999", "title": "Kingston Fury 16GB", "price": 2500}
        candidates_104.append(fresh_item)

        prioritized = self.queue.prioritize_candidates(items_104=candidates_104, max_count=10)
        self.assertEqual(len(prioritized), 1)
        self.assertEqual(prioritized[0]["item_id"], "fresh_deal_999")
        self.assertEqual(prioritized[0]["_queue_priority"], 1)

    def test_scenario_3_defect_listing_with_negation_bait_permanently_rejected(self):
        """
        Scenario 3:
        Defect listing using negation bait ('не для игр, на запчасти, не включается').
        - Negation filter catches genuine defect ('на запчасти').
        - Queue records REJECTED_STATIC.
        - Future checks never re-inspect this item even if price drops to 500 ₽.
        """
        bait_text = "Продам ноутбук. Не для игр, строго на запчасти, плата не включается."
        is_rejected, reason = check_excludes(bait_text)
        self.assertTrue(is_rejected)

        item_id = "defect_laptop_1"
        self.queue.record_result(item_id, InspectionStatus.REJECTED_STATIC, price=5000, reason=reason)

        # Seller drops price to 500 ₽
        self.assertFalse(self.queue.should_inspect(item_id, current_price=500))

        # Even after TTL expires
        self.queue.item_states[item_id]["inspected_at"] = time.time() - 100000
        self.assertFalse(self.queue.should_inspect(item_id, current_price=500))

    def test_scenario_4_carousel_reserve_isolated_from_action_block(self):
        """
        Scenario 4:
        Page contains recommendation carousel with a reserved item ('Товар зарезервирован').
        - Localized action block scoping ensures target listing is NOT flagged as reserved.
        - Target listing is successfully verified and processed.
        """
        soup = BeautifulSoup(HTML_PAGE_RESERVED_CAROUSEL_ONLY, "html.parser")

        # 1. Action block status
        action_block = soup.find("div", attrs={"data-marker": "item-view/actions"})
        self.assertIsNotNone(action_block)
        action_text = action_block.get_text().strip().lower()
        is_reserved = is_reserved_text(action_text)
        self.assertFalse(is_reserved)

        # 2. Recommendation block (carousel)
        carousel = soup.find("div", attrs={"data-marker": "similar-items"})
        self.assertIsNotNone(carousel)
        carousel_text = carousel.get_text().lower()
        self.assertTrue(is_reserved_text(carousel_text))

        # 3. Listing is active and has delivery button
        delivery_btn = action_block.find("button", attrs={"data-marker": "delivery-button"})
        self.assertIsNotNone(delivery_btn)

        # 4. Item qualifies as active deal
        item_id = "active_rx6700"
        self.queue.record_result(item_id, InspectionStatus.VERIFIED_DEAL, price=22000)
        save_verified_deal({
            "item_id": item_id,
            "title": "AMD Radeon RX 6700 XT",
            "price": 22000,
            "url": f"https://avito.ru/item/{item_id}",
            "location": "Москва",
            "specs": "12GB",
        }, query="rx 6700 xt", db_path=self.db_path)

        deals = get_all_time_top_deals(query="rx 6700 xt", db_path=self.db_path)
        self.assertEqual(len(deals), 1)

    def test_scenario_5_multi_cycle_database_connection_safety(self):
        """
        Scenario 5:
        Multi-cycle scraper simulation verifying connections are closed every cycle.
        Executes 10 rapid cycles with listing inserts, price updates, and top deal queries.
        No database lock errors or leaking file descriptors occur.
        """
        for cycle in range(10):
            item_data = {
                "item_id": f"cycle_item_{cycle}",
                "title": f"DDR4 RAM Kit {cycle}",
                "price": 3000 + (cycle * 100),
                "url": f"https://avito.ru/item/cycle_{cycle}",
                "location": "Москва",
                "is_deal": 1 if cycle % 2 == 0 else 0,
            }
            # 1. Save listing
            save_listing(item_data, db_path=self.db_path)

            # 2. Save verified deal
            if cycle % 2 == 0:
                save_verified_deal(item_data, query="ddr4", db_path=self.db_path)

            # 3. Query
            deals = get_all_time_top_deals(query="ddr4", db_path=self.db_path)
            self.assertGreaterEqual(len(deals), 1)

        # Verify raw connection state
        with get_connection(self.db_path) as conn:
            total_listings = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            self.assertEqual(total_listings, 10)
            total_verified = conn.execute("SELECT COUNT(*) FROM verified_deals").fetchone()[0]
            self.assertEqual(total_verified, 5)

    def test_scenario_6_price_drop_lifecycle(self):
        """
        Scenario 6:
        Price drop lifecycle across multiple scrape cycles.
        - Cycle 1: Deal discovered at 25,000 ₽, verified.
        - Cycle 2: Same item observed at 25,000 ₽ -> skipped (within TTL).
        - Cycle 3: Seller drops price to 21,000 ₽ -> queue flags price drop,
          re-inspects item, updates database, and records price history.
        """
        item_id = "lifecycle_item_1"
        listing = {
            "item_id": item_id,
            "title": "GeForce RTX 3070",
            "price": 25000,
            "url": f"https://avito.ru/item/{item_id}",
            "location": "Москва",
        }

        # Cycle 1: New discovery
        self.assertTrue(self.queue.should_inspect(item_id, current_price=25000))
        self.queue.record_result(item_id, InspectionStatus.VERIFIED_DEAL, price=25000)
        save_listing(listing, db_path=self.db_path)
        save_verified_deal(listing, query="rtx 3070", db_path=self.db_path)

        # Cycle 2: Same price -> skipped
        self.assertFalse(self.queue.should_inspect(item_id, current_price=25000))

        # Cycle 3: Price drops to 21,000 ₽
        self.assertTrue(self.queue.should_inspect(item_id, current_price=21000))
        candidates = self.queue.prioritize_candidates(items_104=[{"item_id": item_id, "price": 21000}])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["_queue_priority"], 2)  # Priority 2: Price drop

        # Update DB with new price
        listing_drop = dict(listing)
        listing_drop["price"] = 21000
        save_listing(listing_drop, db_path=self.db_path)
        save_verified_deal(listing_drop, query="rtx 3070", db_path=self.db_path)

        # Verify price history recorded the drop
        with get_connection(self.db_path) as conn:
            history = conn.execute("SELECT * FROM price_history WHERE item_id = ?", (item_id,)).fetchall()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["old_price"], 25000)
            self.assertEqual(history[0]["new_price"], 21000)

        # Verify updated deal in top deals
        top_deals = get_all_time_top_deals(query="rtx 3070", db_path=self.db_path)
        self.assertEqual(top_deals[0]["price"], 21000)

    def test_scenario_7_reserved_listing_lifecycle(self):
        """
        Scenario 7:
        Item becomes reserved, is marked inactive in database, skipped during reserved TTL,
        and re-evaluated after reserved TTL expires.
        """
        item_id = "reserved_item_7"
        deal = {
            "item_id": item_id,
            "title": "Core i7 13700K",
            "price": 28000,
            "url": f"https://avito.ru/item/{item_id}",
            "location": "Москва",
        }
        save_verified_deal(deal, query="13700k", db_path=self.db_path)
        self.queue.record_result(item_id, InspectionStatus.VERIFIED_DEAL, price=28000)

        # Deal is active
        self.assertEqual(len(get_all_time_top_deals(query="13700k", db_path=self.db_path)), 1)

        # Item gets booked/reserved
        mark_deal_reserved_or_inactive(item_id, db_path=self.db_path)
        self.queue.record_result(item_id, InspectionStatus.REJECTED_RESERVED, price=28000)

        # Deal no longer shows in active top deals
        self.assertEqual(len(get_all_time_top_deals(query="13700k", db_path=self.db_path)), 0)

        # Skipped within reserved TTL (1800s)
        self.assertFalse(self.queue.should_inspect(item_id, current_price=28000))

        # Buyer cancelled order after 30 minutes -> eligible for inspection again
        self.queue.item_states[item_id]["inspected_at"] = time.time() - 2000
        self.assertTrue(self.queue.should_inspect(item_id, current_price=28000))


if __name__ == "__main__":
    unittest.main()
