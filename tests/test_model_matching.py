"""Tests for strict model matching: no RTX 2070/3080 in an RTX 3070 search."""

import unittest

from universal_sniper import SearchTarget, title_matches_query


class TestTitleMatchesQuery(unittest.TestCase):
    def test_other_gpu_models_rejected(self):
        self.assertFalse(title_matches_query("Видеокарты Asus Dual RTX2070 8gb gddr6 256bit", "rtx 3070"))
        self.assertFalse(title_matches_query("Видеокарта Asus Rog Strix RTX2070 8gb gddr6", "rtx 3070"))
        self.assertFalse(title_matches_query("В стиле Palit Gamerock 3080", "rtx 3070"))

    def test_same_gpu_model_accepted(self):
        for title in [
            "Rtx 3070",
            "Видеокарта MSI GeForce RTX 3070 Gaming Z Trio 8G",
            "Видеокарта RTX3070 8GB",
            "Palit RTX 3070 JetStream 8G",
        ]:
            with self.subTest(title=title):
                self.assertTrue(title_matches_query(title, "rtx 3070"))

    def test_variant_suffix_rejected_unless_requested(self):
        self.assertFalse(title_matches_query("Видеокарта rtx 3070 ti m 8gb", "rtx 3070"))
        self.assertFalse(title_matches_query("Rtx 3070ti", "rtx 3070"))
        self.assertTrue(title_matches_query("Видеокарта RTX 3070 Ti", "rtx 3070 ti"))

    def test_ram_queries_ignore_capacity_but_require_generation(self):
        self.assertTrue(title_matches_query("Оперативная память netac ddr4 2x8gb 3200", "ddr4 16gb 3200"))
        self.assertTrue(title_matches_query("Patriot 16gb 2x8 Kit 3200Mhz ddr4 PC-25600", "ddr4 16gb 3200"))
        self.assertFalse(title_matches_query("DDR3 8gb 1600", "ddr4 16gb 3200"))

    def test_short_generic_queries_stay_permissive(self):
        self.assertTrue(title_matches_query("Sony PlayStation 5", "ps5"))
        self.assertTrue(title_matches_query("Apple iPhone 13 128GB", "iphone 13 128gb"))

    def test_quick_filter_rejects_other_model(self):
        target = SearchTarget(name="RTX 3070", query="rtx 3070")
        item = {
            "item_id": "junk_1",
            "title": "Видеокарта Asus Dual RTX2070 8gb gddr6 256bit",
            "raw_description": "Отличное состояние",
            "price": 24000,
        }
        ok, reason = target.quick_filter(item)
        self.assertFalse(ok)
        self.assertIn("модель", reason.lower())

    def test_mobile_gpu_excluded_by_default(self):
        target = SearchTarget(name="RTX 3070", query="rtx 3070")
        item = {
            "item_id": "mob_1",
            "title": "Видеокарта RTX 3070m 8GB для ноутбука",
            "raw_description": "Отличное состояние",
            "price": 18000,
        }
        ok, reason = target.quick_filter(item)
        self.assertFalse(ok)
        self.assertIn("мобильная", reason.lower())

    def test_mobile_gpu_allowed_when_filter_off(self):
        target = SearchTarget(name="RTX 3070", query="rtx 3070", exclude_mobile=False)
        self.assertTrue(target.allow_mobile)
        item = {
            "item_id": "mob_2",
            "title": "Видеокарта RTX 3070m 8GB для ноутбука",
            "raw_description": "Отличное состояние",
            "price": 18000,
        }
        ok, reason = target.quick_filter(item)
        self.assertTrue(ok, reason)

    def test_mobile_suffix_matching(self):
        self.assertFalse(title_matches_query("RTX 3070m 8GB", "rtx 3070"))
        self.assertTrue(title_matches_query("RTX 3070m 8GB", "rtx 3070", allow_mobile=True))


if __name__ == "__main__":
    unittest.main()
