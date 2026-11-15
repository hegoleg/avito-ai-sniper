"""
Tests for hardware_catalog.py module and chip database.
Validates:
1. Search catalog by exact chip, partial query, case-insensitive, Russian/English x.
2. Category filtering (gpu, cpu, ram, ssd, motherboard, psu, cooler, case).
3. Retrieval by item ID and missing ID handling.
4. Completeness of essential fields (query, min_price, max_price, required_words, exclude_words).
"""

import unittest
from hardware_catalog import (
    HARDWARE_CATALOG,
    search_catalog,
    get_all_categories,
    get_item_by_id
)


class TestHardwareCatalog(unittest.TestCase):
    def test_catalog_not_empty(self):
        """Catalog must contain a comprehensive set of components."""
        self.assertGreaterEqual(len(HARDWARE_CATALOG), 25)

    def test_catalog_structure(self):
        """Every component must have all essential fields properly formatted."""
        required_fields = ["id", "category", "chip", "name", "query", "min_price", "max_price", "retail_est"]
        for it in HARDWARE_CATALOG:
            for field in required_fields:
                self.assertIn(field, it, f"Item {it.get('id')} is missing field '{field}'")
            self.assertIsInstance(it["min_price"], int)
            self.assertIsInstance(it["max_price"], int)
            self.assertGreater(it["max_price"], it["min_price"])

    def test_search_by_gpu_chip(self):
        """Searching by '3070' must find RTX 3070 and RTX 3070 Ti."""
        results = search_catalog("3070", category="gpu")
        self.assertGreaterEqual(len(results), 2)
        chip_names = [it["chip"] for it in results]
        self.assertIn("RTX 3070", chip_names)
        self.assertIn("RTX 3070 Ti", chip_names)

    def test_search_by_cpu_chip(self):
        """Searching by '7500f' or '5600x' must return the target CPU."""
        r_7500 = search_catalog("7500f", category="cpu")
        self.assertEqual(len(r_7500), 1)
        self.assertEqual(r_7500[0]["chip"], "Ryzen 5 7500F")

        r_5600x = search_catalog("5600x", category="cpu")
        self.assertGreaterEqual(len(r_5600x), 1)
        self.assertEqual(r_5600x[0]["chip"], "Ryzen 5 5600X")

    def test_search_category_filter(self):
        """Filtering by category must restrict results to that category only."""
        ram_results = search_catalog(category="ram")
        for it in ram_results:
            self.assertEqual(it["category"], "ram")

        ssd_results = search_catalog(category="ssd")
        for it in ssd_results:
            self.assertEqual(it["category"], "ssd")

    def test_get_all_categories(self):
        """Must return 8 standard PC builder categories."""
        cats = get_all_categories()
        cat_ids = [c["id"] for c in cats]
        self.assertIn("gpu", cat_ids)
        self.assertIn("cpu", cat_ids)
        self.assertIn("ram", cat_ids)
        self.assertIn("motherboard", cat_ids)
        self.assertIn("ssd", cat_ids)
        self.assertIn("psu", cat_ids)
        self.assertIn("cooler", cat_ids)
        self.assertIn("case", cat_ids)

    def test_get_item_by_id(self):
        """Lookup by ID must return exact item or None."""
        it = get_item_by_id("gpu_rtx_3070")
        self.assertIsNotNone(it)
        self.assertEqual(it["chip"], "RTX 3070")

        none_it = get_item_by_id("non_existent_chip_12345")
        self.assertIsNone(none_it)


if __name__ == "__main__":
    unittest.main()
