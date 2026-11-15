"""
Tests for Verification Queue, Anti-ban utilities, and Action Block Reserve Scoping.
Validates Tier 1, 2, and 3 specifications.
Compatible with pytest and unittest.
"""

import os
import time
import tempfile
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from bs4 import BeautifulSoup

from verification_queue import (
    InspectionStatus,
    QueuedItem,
    VerificationQueue,
    BackoffManager,
    async_sleep_jitter,
    async_request_pause,
)
from negation_filter import is_reserved_text
from tests.conftest import (
    HTML_PAGE_RESERVED_ACTION,
    HTML_PAGE_RESERVED_CAROUSEL_ONLY,
    HTML_PAGE_CLOSED_WARNING,
    HTML_PAGE_ACTIVE_DELIVERY,
    make_mock_item,
)


class TestVerificationQueueDeduplication(unittest.TestCase):
    """Tier 1: VerificationQueue inspection rules, deduplication, TTL, and price drops."""

    def setUp(self):
        self.queue = VerificationQueue(cache_ttl_seconds=7200, reserved_ttl_seconds=1800)

    def test_unseen_item_is_inspected(self):
        """Rule 1: An unseen item ID must always be inspected."""
        self.assertTrue(self.queue.should_inspect("item_001", current_price=10000))

    def test_verified_deal_within_ttl_is_skipped(self):
        """Rule 4: A verified deal within cache_ttl (2 hours) must be skipped."""
        self.queue.record_result("item_001", InspectionStatus.VERIFIED_DEAL, price=10000)
        self.assertFalse(self.queue.should_inspect("item_001", current_price=10000))

    def test_verified_deal_after_ttl_is_inspected(self):
        """Rule 6: A verified deal after cache_ttl expires should be re-inspected."""
        self.queue.record_result("item_001", InspectionStatus.VERIFIED_DEAL, price=10000)
        # Simulate time passage beyond 7200s
        self.queue.item_states["item_001"]["inspected_at"] = time.time() - 7500
        self.assertTrue(self.queue.should_inspect("item_001", current_price=10000))

    def test_price_drop_triggers_reinspection(self):
        """Rule 3: Price drop on a known item must trigger re-inspection even within TTL."""
        self.queue.record_result("item_001", InspectionStatus.VERIFIED_DEAL, price=20000)
        # Price drops from 20000 to 18000
        self.assertTrue(self.queue.should_inspect("item_001", current_price=18000))

    def test_price_increase_or_same_within_ttl_skipped(self):
        """Price increase or identical price does NOT trigger re-inspection within TTL."""
        self.queue.record_result("item_001", InspectionStatus.VERIFIED_DEAL, price=20000)
        # Same price
        self.assertFalse(self.queue.should_inspect("item_001", current_price=20000))
        # Higher price
        self.assertFalse(self.queue.should_inspect("item_001", current_price=22000))

    def test_permanent_defect_rejected_static_never_reinspected(self):
        """Rule 2: REJECTED_STATIC items must NEVER be re-inspected even with price drop or expired TTL."""
        self.queue.record_result("item_defect", InspectionStatus.REJECTED_STATIC, price=15000, reason="Битая")
        # Same price
        self.assertFalse(self.queue.should_inspect("item_defect", current_price=15000))
        # Price drop to 5000
        self.assertFalse(self.queue.should_inspect("item_defect", current_price=5000))
        # Expired TTL
        self.queue.item_states["item_defect"]["inspected_at"] = time.time() - 100000
        self.assertFalse(self.queue.should_inspect("item_defect", current_price=5000))

    def test_rejected_reserved_ttl(self):
        """Rule 5: REJECTED_RESERVED skipped within 1800s, re-inspected after 1800s."""
        self.queue.record_result("item_res", InspectionStatus.REJECTED_RESERVED, price=12000)
        # Within reserved TTL
        self.assertFalse(self.queue.should_inspect("item_res", current_price=12000))
        # After reserved TTL expired (e.g. 1900s)
        self.queue.item_states["item_res"]["inspected_at"] = time.time() - 1900
        self.assertTrue(self.queue.should_inspect("item_res", current_price=12000))


class TestVerificationQueuePrioritization(unittest.TestCase):
    """Tier 1 & 2: Priority sorting, candidate limits, and cross-source deduplication."""

    def setUp(self):
        self.queue = VerificationQueue()

    def test_priority_ordering_fresh_104_ahead_of_cheapest_1(self):
        """Fresh uninspected items from s=104 (priority 1) rank ahead of s=1 (priority 3)."""
        items_104 = [
            {"item_id": "fresh_1", "title": "Fresh 1", "price": 5000},
            {"item_id": "fresh_2", "title": "Fresh 2", "price": 4000},
        ]
        items_1 = [
            {"item_id": "cheap_1", "title": "Cheap 1", "price": 3000},
            {"item_id": "cheap_2", "title": "Cheap 2", "price": 3500},
        ]

        candidates = self.queue.prioritize_candidates(items_104=items_104, items_1=items_1, max_count=4)
        self.assertEqual(len(candidates), 4)
        # Highest priority (1): fresh_2 (price 4000), then fresh_1 (price 5000)
        self.assertEqual(candidates[0]["item_id"], "fresh_2")
        self.assertEqual(candidates[1]["item_id"], "fresh_1")
        # Then priority 3: cheap_1 (price 3000), then cheap_2 (price 3500)
        self.assertEqual(candidates[2]["item_id"], "cheap_1")
        self.assertEqual(candidates[3]["item_id"], "cheap_2")

    def test_priority_ordering_price_drop_ahead_of_cheapest(self):
        """Price drop on known item (priority 2) ranks ahead of s=1 uninspected (priority 3)."""
        # Record known item at 10000
        self.queue.record_result("known_drop", InspectionStatus.VERIFIED_DEAL, price=10000)

        items_104 = [
            {"item_id": "known_drop", "title": "Price Dropped Item", "price": 7000},
        ]
        items_1 = [
            {"item_id": "cheap_new", "title": "Cheap New Item", "price": 2000},
        ]

        candidates = self.queue.prioritize_candidates(items_104=items_104, items_1=items_1, max_count=2)
        # known_drop is priority 2, cheap_new is priority 3
        self.assertEqual(candidates[0]["item_id"], "known_drop")
        self.assertEqual(candidates[0]["_queue_priority"], 2)
        self.assertEqual(candidates[1]["item_id"], "cheap_new")
        self.assertEqual(candidates[1]["_queue_priority"], 3)

    def test_deduplication_between_104_and_1(self):
        """If an item appears in both s=104 and s=1, it is enqueued only once with highest priority."""
        duplicate_item = {"item_id": "dup_item", "title": "Item in both sorts", "price": 6000}
        candidates = self.queue.prioritize_candidates(items_104=[duplicate_item], items_1=[duplicate_item], max_count=5)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["item_id"], "dup_item")
        self.assertEqual(candidates[0]["_source_sort"], "104")
        self.assertEqual(candidates[0]["_queue_priority"], 1)

    def test_max_count_truncation(self):
        """Queue candidate list must strictly respect max_count."""
        items = [{"item_id": f"item_{i}", "title": f"Item {i}", "price": 1000 + i} for i in range(20)]
        candidates = self.queue.prioritize_candidates(items_104=items, max_count=7)
        self.assertEqual(len(candidates), 7)


class TestVerificationQueuePersistenceAndStats(unittest.TestCase):
    """Tier 2: Cache file persistence, JSON serialization, and stats calculation."""

    def test_json_save_and_load(self):
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            q1 = VerificationQueue(cache_file=tmp_path)
            q1.record_result("item_101", InspectionStatus.VERIFIED_DEAL, price=5000, reason="Good Deal")
            q1.record_result("item_102", InspectionStatus.REJECTED_STATIC, price=3000, reason="Defect")
            q1.record_result("item_103", InspectionStatus.REJECTED_RESERVED, price=4500, reason="Reserved")

            # Load into fresh instance
            q2 = VerificationQueue(cache_file=tmp_path)
            self.assertEqual(len(q2), 3)
            self.assertEqual(q2.get_status("item_101"), InspectionStatus.VERIFIED_DEAL)
            self.assertEqual(q2.get_status("item_102"), InspectionStatus.REJECTED_STATIC)
            self.assertEqual(q2.get_status("item_103"), InspectionStatus.REJECTED_RESERVED)

            stats = q2.get_stats()
            self.assertEqual(stats["total_tracked"], 3)
            self.assertEqual(stats["verified_deal"], 1)
            self.assertEqual(stats["rejected_static"], 1)
            self.assertEqual(stats["rejected_reserved"], 1)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestAntiBanJitterAndBackoff(unittest.TestCase):
    """Tier 2: Randomized pauses, jitter ranges, and exponential backoff manager."""

    def test_backoff_manager_progression(self):
        bm = BackoffManager(base_delay=10.0, max_delay=100.0, jitter_min=1.0, jitter_max=2.0)
        self.assertFalse(bm.is_backing_off)

        # 1st error: base * 2^0 = 10 + [1, 2] -> ~11-12
        d1 = bm.record_error()
        self.assertTrue(bm.is_backing_off)
        self.assertGreaterEqual(d1, 11.0)
        self.assertLessEqual(d1, 12.0)

        # 2nd error: base * 2^1 = 20 + [1, 2] -> ~21-22
        d2 = bm.record_error()
        self.assertGreaterEqual(d2, 21.0)
        self.assertLessEqual(d2, 22.0)

        # 3rd error: base * 2^2 = 40 + [1, 2] -> ~41-42
        d3 = bm.record_error()
        self.assertGreaterEqual(d3, 41.0)
        self.assertLessEqual(d3, 42.0)

        # Success resets backoff
        bm.record_success()
        self.assertFalse(bm.is_backing_off)
        self.assertEqual(bm.consecutive_errors, 0)
        self.assertEqual(bm.last_delay, 0.0)

    def test_backoff_ceiling(self):
        bm = BackoffManager(base_delay=50.0, max_delay=120.0, jitter_min=1.0, jitter_max=5.0)
        for _ in range(10):
            d = bm.record_error()
        self.assertLessEqual(d, 120.0)

    def test_async_sleep_jitter_range(self):
        async def run_jitter():
            duration = await async_sleep_jitter(base_sec=0.01, jitter_pct=0.20)
            self.assertGreaterEqual(duration, 0.0079)
            self.assertLessEqual(duration, 0.0121)

        asyncio.run(run_jitter())

    def test_async_request_pause_range(self):
        async def run_pause():
            duration = await async_request_pause(min_sec=0.01, max_sec=0.02)
            self.assertGreaterEqual(duration, 0.0099)
            self.assertLessEqual(duration, 0.0201)

        asyncio.run(run_pause())


class TestActionBlockReserveScoping(unittest.TestCase):
    """Tier 1 & 2: Localized reserve checking strictly inside action block vs carousels."""

    def test_reserved_indicator_in_action_block_detected(self):
        """When action block explicitly states 'Товар зарезервирован', is_reserved == True."""
        soup = BeautifulSoup(HTML_PAGE_RESERVED_ACTION, "html.parser")
        action_block = soup.find("div", attrs={"data-marker": "item-view/actions"})
        self.assertIsNotNone(action_block)
        action_text = action_block.get_text().strip().lower()
        self.assertTrue(is_reserved_text(action_text))

    def test_reserved_in_carousel_ignored_by_scoped_action_block(self):
        """Crucial test: recommendation carousel has reserved item, but action block is available."""
        soup = BeautifulSoup(HTML_PAGE_RESERVED_CAROUSEL_ONLY, "html.parser")

        # Whole page body text contains 'зарезервирован' from recommendations
        full_body_text = soup.body.get_text().lower()
        self.assertIn("зарезервирован", full_body_text)

        # BUT the scoped action container has NO reservation and has active delivery button!
        action_block = soup.find("div", attrs={"data-marker": "item-view/actions"})
        self.assertIsNotNone(action_block)
        action_text = action_block.get_text().strip().lower()
        self.assertFalse(is_reserved_text(action_text))

        # Check delivery button
        delivery_btn = action_block.find("button", attrs={"data-marker": "delivery-button"})
        self.assertIsNotNone(delivery_btn)

    def test_closed_warning_banner_detected(self):
        soup = BeautifulSoup(HTML_PAGE_CLOSED_WARNING, "html.parser")
        closed_el = soup.find("div", attrs={"data-marker": "item-view/closed-warning"})
        self.assertIsNotNone(closed_el)
        closed_text = closed_el.get_text().lower()
        self.assertTrue(any(p in closed_text for p in ["закрыто", "снято с публикации", "товар продан"]))

    def test_active_delivery_details_extracted(self):
        soup = BeautifulSoup(HTML_PAGE_ACTIVE_DELIVERY, "html.parser")
        action_block = soup.find("div", attrs={"data-marker": "item-view/actions"})
        self.assertIsNotNone(action_block)
        action_text = action_block.get_text().strip().lower()
        self.assertFalse(is_reserved_text(action_text))

        delivery_status = soup.find("div", attrs={"data-marker": "delivery-item-status"})
        self.assertIsNotNone(delivery_status)
        self.assertIn("доставка", delivery_status.get_text().lower())

        seller_name = soup.find("div", attrs={"data-marker": "seller-info/name"})
        self.assertIn("Иван Компьютерный", seller_name.get_text())


if __name__ == "__main__":
    unittest.main()
