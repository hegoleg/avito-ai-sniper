"""
Tests for price parsing logic: clean_price and DOM price extraction.
Validates Tier 1 (standard) and Tier 2 (boundary, discounts, strikethrough) specifications.
Compatible with pytest and unittest.
"""

import unittest
from bs4 import BeautifulSoup
from scraper import clean_price
from tests.conftest import (
    HTML_CARD_STANDARD_PRICE,
    HTML_CARD_DISCOUNT_OLD_PRICE,
    HTML_CARD_DISCOUNT_PERCENT,
    HTML_CARD_META_PRICE,
)


class TestCleanPriceStandard(unittest.TestCase):
    """Tier 1: Standard price formats."""

    def test_ruble_symbol(self):
        self.assertEqual(clean_price("2 500 ₽"), 2500)
        self.assertEqual(clean_price("500 ₽"), 500)
        self.assertEqual(clean_price("125 000 ₽"), 125000)

    def test_rub_text(self):
        self.assertEqual(clean_price("15 000 руб."), 15000)
        self.assertEqual(clean_price("3 500 руб"), 3500)
        self.assertEqual(clean_price("1 000 рублей"), 1000)

    def test_short_r(self):
        self.assertEqual(clean_price("2500 р"), 2500)
        self.assertEqual(clean_price("4500 р."), 4500)
        self.assertEqual(clean_price("10000р"), 10000)

    def test_plain_digits_no_currency(self):
        self.assertEqual(clean_price("15000"), 15000)
        self.assertEqual(clean_price("2500"), 2500)
        self.assertEqual(clean_price("120000"), 120000)

    def test_price_with_prefix(self):
        self.assertEqual(clean_price("от 4 500 ₽"), 4500)
        self.assertEqual(clean_price("до 10 000 ₽"), 10000)
        self.assertEqual(clean_price("примерно 3 000 руб."), 3000)


class TestCleanPriceDiscountsAndStrikethrough(unittest.TestCase):
    """Tier 2: Strikethrough, old prices, discount badges, and concatenation prevention."""

    def test_strikethrough_isolation_cardinal_bug(self):
        """Crucial requirement: '10 500 ₽ 12 000 ₽' must NOT become 1050012000."""
        result = clean_price("10 500 ₽ 12 000 ₽")
        self.assertNotEqual(result, 1050012000)
        self.assertEqual(result, 10500)

    def test_strikethrough_price_two_ruble_symbols(self):
        self.assertEqual(clean_price("2 500 ₽ 3 000 ₽"), 2500)
        self.assertEqual(clean_price("18 000 ₽ 25 000 ₽"), 18000)

    def test_discount_with_percentage_badge(self):
        self.assertEqual(clean_price("2 500 ₽ -17% 3 000 ₽"), 2500)
        self.assertEqual(clean_price("14 990 ₽ -25% 19 990 ₽"), 14990)

    def test_discount_with_percentage_prefix(self):
        self.assertEqual(clean_price("-17% 2 500 ₽ 3 000 ₽"), 2500)
        self.assertEqual(clean_price("-30% 10 000 ₽"), 10000)

    def test_discount_with_explanatory_text(self):
        self.assertEqual(clean_price("4 000 ₽ (скидка 500 ₽)"), 4000)
        self.assertEqual(clean_price("2 500 ₽ старая цена 3 000 ₽"), 2500)

    def test_discount_with_rub_word(self):
        self.assertEqual(clean_price("10 500 руб. 12 000 руб."), 10500)
        self.assertEqual(clean_price("2 500 руб -10% 3 000 руб"), 2500)


class TestCleanPriceWhitespaceAndFormatting(unittest.TestCase):
    """Tier 2: Non-breaking spaces, multiline blocks, and whitespace."""

    def test_multiline_old_price_below(self):
        self.assertEqual(clean_price("2 500 ₽\n3 000 ₽"), 2500)
        self.assertEqual(clean_price("18 000 ₽\r\n22 000 ₽"), 18000)

    def test_multiline_with_empty_leading_trailing_lines(self):
        self.assertEqual(clean_price("\n\n  18 000 ₽  \n  22 000 ₽\n"), 18000)

    def test_non_breaking_spaces(self):
        self.assertEqual(clean_price("2\xa0500\xa0₽"), 2500)
        self.assertEqual(clean_price("10\xa0000\xa0руб."), 10000)
        self.assertEqual(clean_price("10\xa0500\xa0₽\xa012\xa0000\xa0₽"), 10500)

    def test_leading_trailing_spaces(self):
        self.assertEqual(clean_price("   2 500   ₽   "), 2500)
        self.assertEqual(clean_price("  50 000  руб.  "), 50000)


class TestCleanPriceInvalidInputs(unittest.TestCase):
    """Tier 2: Empty, None, non-string, and invalid text inputs."""

    def test_empty_string(self):
        self.assertIsNone(clean_price(""))

    def test_whitespace_only(self):
        self.assertIsNone(clean_price("   \n\t  "))

    def test_none_input(self):
        self.assertIsNone(clean_price(None))

    def test_non_string_types(self):
        self.assertIsNone(clean_price(12345))
        self.assertIsNone(clean_price(["2500"]))
        self.assertIsNone(clean_price({}))

    def test_text_price_on_request(self):
        self.assertIsNone(clean_price("Цена по запросу"))
        self.assertIsNone(clean_price("Цена договорная"))

    def test_text_free_or_exchange(self):
        self.assertIsNone(clean_price("Бесплатно"))
        self.assertIsNone(clean_price("Договорная"))
        self.assertIsNone(clean_price("Обмен"))

    def test_pure_letters_or_currency_sign(self):
        self.assertIsNone(clean_price("abc"))
        self.assertIsNone(clean_price("₽"))
        self.assertIsNone(clean_price("руб"))


class TestCleanPriceDecimalKopecks(unittest.TestCase):
    """Tier 2: Decimal kopecks handling (Fix 3)."""

    def test_decimal_dot_kopecks(self):
        self.assertEqual(clean_price("2 500.00 ₽"), 2500)
        self.assertEqual(clean_price("10 000.00 ₽"), 10000)

    def test_decimal_comma_kopecks(self):
        self.assertEqual(clean_price("2 500,00 ₽"), 2500)
        self.assertEqual(clean_price("15 000,00 ₽"), 15000)

    def test_decimal_non_zero_kopecks(self):
        self.assertEqual(clean_price("2500.50 ₽"), 2500)
        self.assertEqual(clean_price("2500,50 ₽"), 2500)
        self.assertEqual(clean_price("125 499,99 ₽"), 125499)

    def test_decimal_with_rub_variants(self):
        self.assertEqual(clean_price("10 500.00 руб"), 10500)
        self.assertEqual(clean_price("10 500.00 руб."), 10500)
        self.assertEqual(clean_price("10 500,50 р"), 10500)
        self.assertEqual(clean_price("10 500,50 р."), 10500)

    def test_decimal_no_currency(self):
        self.assertEqual(clean_price("2500.00"), 2500)
        self.assertEqual(clean_price("2500,50"), 2500)

    def test_decimal_strikethrough_isolation(self):
        self.assertEqual(clean_price("2 500,50 ₽ 3 000,00 ₽"), 2500)
        self.assertEqual(clean_price("18 000.00 ₽ -10% 20 000.00 ₽"), 18000)


class TestScraperReserveScopingDOM(unittest.IsolatedAsyncioTestCase):
    """Verification of Scraper Fix 1: Localized action block & main container scoping."""

    async def test_carousel_reserved_element_ignored_by_scoped_selectors(self):
        import tempfile
        from unittest.mock import AsyncMock, MagicMock
        from scraper import AvitoScraper

        mock_cfg = MagicMock()
        mock_cfg.user_data_dir = tempfile.gettempdir()
        mock_cfg.headless = True
        scraper = AvitoScraper(mock_cfg)

        mock_delivery_btn = AsyncMock()
        mock_delivery_btn.inner_text = AsyncMock(return_value="Купить с доставкой")

        mock_action_block = AsyncMock()
        mock_action_block.inner_text = AsyncMock(return_value="Купить с доставкой 2500 ₽")

        async def action_query(sel):
            if "delivery-button" in sel or "button" in sel:
                return mock_delivery_btn
            return None

        mock_action_block.query_selector = AsyncMock(side_effect=action_query)

        mock_main_container = AsyncMock()
        # closed-warning is not inside main container
        mock_main_container.query_selector = AsyncMock(return_value=None)

        mock_tab = AsyncMock()
        mock_tab.goto = AsyncMock()
        mock_tab.wait_for_timeout = AsyncMock()
        mock_tab.close = AsyncMock()

        async def fake_tab_query(sel):
            if '[data-marker="item-view"], main' in sel:
                return mock_main_container
            if '[data-marker="item-view/actions"]' in sel:
                return mock_action_block
            # Carousel elements or fallback item-view queries return None
            return None

        mock_tab.query_selector = AsyncMock(side_effect=fake_tab_query)
        mock_tab.query_selector_all = AsyncMock(return_value=[])

        scraper._context = MagicMock()
        scraper._context.new_page = AsyncMock(return_value=mock_tab)

        details = await scraper.get_item_full_details("https://www.avito.ru/item/12345")
        self.assertFalse(details["is_page_reserved"])
        self.assertFalse(details["is_closed"])
        self.assertTrue(details["has_delivery"])


class TestDOMPriceExtractionScenarios(unittest.TestCase):
    """Tier 1 & 2: Simulating DOM extraction logic used in _extract_items_from_page."""

    def test_meta_price_prioritization(self):
        """When meta[itemprop='price'] is present, its value should take priority."""
        soup = BeautifulSoup(HTML_CARD_META_PRICE, "html.parser")
        meta_tag = soup.find("meta", attrs={"itemprop": "price"})
        self.assertIsNotNone(meta_tag)
        content = meta_tag.get("content")
        self.assertEqual(int(content), 7500)

    def test_dom_active_price_isolated_from_old_price(self):
        """When old price element exists, active price tag is isolated."""
        soup = BeautifulSoup(HTML_CARD_DISCOUNT_OLD_PRICE, "html.parser")
        price_container = soup.find("div", attrs={"data-marker": "item-price"})
        self.assertIsNotNone(price_container)

        # Active price element
        active_el = price_container.find("strong")
        self.assertIsNotNone(active_el)
        self.assertEqual(clean_price(active_el.get_text()), 10500)

        # Even if raw text of the entire container is passed, clean_price must return 10500
        full_container_text = price_container.get_text()
        self.assertEqual(clean_price(full_container_text), 10500)

    def test_dom_discount_percentage_badge(self):
        soup = BeautifulSoup(HTML_CARD_DISCOUNT_PERCENT, "html.parser")
        price_container = soup.find("div", attrs={"data-marker": "item-price"})
        self.assertIsNotNone(price_container)
        full_text = price_container.get_text()
        self.assertEqual(clean_price(full_text), 2500)


if __name__ == "__main__":
    unittest.main()
