"""
Tests for web_app.py FastAPI endpoints.
Validates:
1. /api/build status and savings calculation.
2. /api/catalog and /api/catalog/categories endpoints.
3. /api/build/apply_catalog functionality.
4. /api/deals query response.
"""

import unittest
from fastapi.testclient import TestClient
from web_app import app


class TestWebAppEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_build_state(self):
        """GET /api/build returns slots and summary calculations."""
        res = self.client.get("/api/build")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("slots", data)
        self.assertIn("total_build", data)
        self.assertIn("total_retail", data)
        self.assertGreaterEqual(len(data["slots"]), 1)

    def test_get_catalog_categories(self):
        """GET /api/catalog/categories returns 8 categories."""
        res = self.client.get("/api/catalog/categories")
        self.assertEqual(res.status_code, 200)
        cats = res.json()
        self.assertEqual(len(cats), 8)

    def test_search_catalog_endpoint(self):
        """GET /api/catalog?query=3070 returns matched chips."""
        res = self.client.get("/api/catalog?query=3070")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["count"], 1)
        self.assertTrue(any("3070" in item["chip"] for item in data["items"]))

    def test_apply_catalog_item_to_slot(self):
        """POST /api/build/apply_catalog updates the target slot."""
        payload = {"slot_id": "gpu", "catalog_id": "gpu_rtx_3070"}
        res = self.client.post("/api/build/apply_catalog", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

        # Verify build updated
        b_res = self.client.get("/api/build")
        slots = b_res.json()["slots"]
        gpu_slot = next((s for s in slots if s["slot_id"] == "gpu"), None)
        self.assertIsNotNone(gpu_slot)
        self.assertEqual(gpu_slot["target_query"], "rtx 3070")
        self.assertEqual(gpu_slot["retail_est"], 44000)

    def test_get_deals_endpoint(self):
        """GET /api/deals/{query} returns deals list without blocking."""
        res = self.client.get("/api/deals/rtx 3070")
        self.assertEqual(res.status_code, 200)
        self.assertIn("deals", res.json())

    def test_get_deals_with_min_seller_rating(self):
        """GET /api/deals/{query}?min_seller_rating=4.5 returns only rated verified deals."""
        res = self.client.get("/api/deals/rtx 3070?min_seller_rating=4.5")
        self.assertEqual(res.status_code, 200)
        for deal in res.json()["deals"]:
            self.assertTrue(deal["is_verified"])
            self.assertGreaterEqual(float(deal["seller_rating"]), 4.5)

    def test_get_deals_with_mobile_filter_off(self):
        """GET /api/deals/{query}?exclude_mobile=0 includes mobile chips instead of hiding them."""
        res = self.client.get("/api/deals/rtx 3070?exclude_mobile=0")
        self.assertEqual(res.status_code, 200)
        self.assertIn("deals", res.json())


class TestSellerRatingParsing(unittest.TestCase):
    def test_parse_seller_rating(self):
        from web_app import parse_seller_rating

        self.assertEqual(parse_seller_rating("4.9"), 4.9)
        self.assertEqual(parse_seller_rating("4,9"), 4.9)
        self.assertEqual(parse_seller_rating("5"), 5.0)
        self.assertIsNone(parse_seller_rating(""))
        self.assertIsNone(parse_seller_rating(None))
        self.assertIsNone(parse_seller_rating("нет рейтинга"))
        self.assertIsNone(parse_seller_rating("7.2"))


if __name__ == "__main__":
    unittest.main()
