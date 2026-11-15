"""
Tests for Requirement R3: Unified Telegram Pipeline, Captcha Alerts & Runner Consolidation.
Validates:
1. Universal deal card formatting in TelegramNotifier for various hardware categories (GPU, CPU, RAM).
2. Async deal alerts and captcha photo alerts with fallback in TelegramNotifier.
3. Captcha and IP block detection hooking in AvitoScraper._handle_captcha.
4. UniversalSniper runner filtering, queue integration, and CLI options.
5. Sniper DDR4 canonical forwarder delegation.
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from config import load_config
from notifier import TelegramNotifier
from scraper import AvitoScraper
from universal_sniper import SearchTarget, load_presets


class TestTelegramNotifierFormatting(unittest.TestCase):
    def setUp(self):
        self.notifier = TelegramNotifier()

    def test_format_universal_gpu_has_no_ram_hardcoding(self):
        """GPU deal card must format cleanly without RAM-specific placeholders."""
        item = {
            "item_id": "gpu_123",
            "title": "MSI GeForce RTX 3070 Gaming X Trio 8GB",
            "price": 28500,
            "estimated_market_price": 34000,
            "specs": "8GB GDDR6, 256 bit",
            "location": "Москва",
            "deal_rating": "TOP_DEAL",
            "url": "https://www.avito.ru/item/gpu_123"
        }
        msg = self.notifier.format_universal_message(item, target_name="RTX 3070")

        self.assertIn("🔥 <b>НАХОДКА! СУПЕРЦЕНА НА АВИТО</b>", msg)
        self.assertIn("MSI GeForce RTX 3070 Gaming X Trio 8GB", msg)
        self.assertIn("28 500 ₽", msg)
        self.assertIn("34 000 ₽", msg)
        self.assertIn("8GB GDDR6, 256 bit", msg)
        self.assertIn("Москва", msg)
        self.assertIn("https://www.avito.ru/item/gpu_123", msg)

        # Ensure NO RAM-specific leakage occurs for GPU items
        self.assertNotIn("Память: RAM", msg)
        self.assertNotIn("🖥 Память", msg)
        self.assertNotIn("DIMM", msg)

    def test_format_universal_cpu(self):
        """CPU deal card formats target name and specs cleanly."""
        item = {
            "item_id": "cpu_456",
            "title": "AMD Ryzen 5 5600 AM4 Box",
            "price": 8200,
            "location": "Санкт-Петербург",
            "deal_rating": "GOOD_DEAL",
            "url": "https://www.avito.ru/item/cpu_456"
        }
        msg = self.notifier.format_universal_message(item, target_name="Ryzen 5600")

        self.assertIn("⚡ <b>ВЫГОДНОЕ ПРЕДЛОЖЕНИЕ НА АВИТО</b>", msg)
        self.assertIn("AMD Ryzen 5 5600 AM4 Box", msg)
        self.assertIn("8 200 ₽", msg)
        self.assertIn("Ryzen 5600", msg)
        self.assertNotIn("Память: RAM", msg)

    def test_format_universal_ram_includes_memory_attributes(self):
        """RAM deal card includes type, capacity, kit, and frequency when available."""
        item = {
            "item_id": "ram_789",
            "title": "Kingston Fury Beast DDR4 16GB (2x8GB) 3200MHz",
            "price": 2300,
            "ram_type": "DDR4",
            "capacity_gb": 16,
            "is_kit": True,
            "frequency_mhz": 3200,
            "form_factor": "DESKTOP_DIMM",
            "location": "Казань",
            "deal_rating": "TOP_DEAL",
            "url": "https://www.avito.ru/item/ram_789"
        }
        msg = self.notifier.format_universal_message(item)

        self.assertIn("DDR4", msg)
        self.assertIn("16 ГБ", msg)
        self.assertIn("(комплект)", msg)
        self.assertIn("3200 МГц", msg)
        self.assertIn("🖥 Для ПК (DIMM)", msg)

    def test_format_message_backward_compatibility(self):
        """Legacy format_message delegates to format_universal_message."""
        item = {
            "item_id": "legacy_1",
            "title": "Test Item",
            "price": 1000,
            "url": "https://avito.ru"
        }
        self.assertEqual(
            self.notifier.format_message(item),
            self.notifier.format_universal_message(item)
        )


class TestTelegramNotifierDispatch(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_console_fallback(self):
        """When token/chat_id are empty, sending alerts prints to console and returns True."""
        notifier = TelegramNotifier(bot_token="", chat_id="")
        self.assertFalse(notifier.is_configured)

        deal_res = await notifier.send_deal_alert({"title": "Test", "price": 500, "url": "https://avito.ru"})
        self.assertTrue(deal_res)

        captcha_res = await notifier.send_captcha_alert(
            reason="GeeTest",
            page_url="https://avito.ru",
            headless=True
        )
        self.assertTrue(captcha_res)

    @patch("httpx.AsyncClient.post")
    async def test_send_deal_alert_async_http(self, mock_post):
        """When configured, send_deal_alert dispatches JSON payload with inline keyboard."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = TelegramNotifier(bot_token="12345:ABCDE", chat_id="998877")
        self.assertTrue(notifier.is_configured)

        item = {
            "item_id": "test_deal_1",
            "title": "RTX 3070 Deal",
            "price": 25000,
            "url": "https://www.avito.ru/item/test_deal_1"
        }
        result = await notifier.send_deal_alert(item, target_name="RTX 3070")

        self.assertTrue(result)
        self.assertTrue(mock_post.called)
        call_kwargs = mock_post.call_args.kwargs
        json_payload = call_kwargs.get("json", {})
        self.assertEqual(json_payload.get("chat_id"), "998877")
        self.assertIn("RTX 3070 Deal", json_payload.get("text", ""))
        self.assertIn("reply_markup", json_payload)

    @patch("httpx.AsyncClient.post")
    async def test_send_captcha_alert_with_photo(self, mock_post):
        """When screenshot exists, send_captcha_alert posts to sendPhoto endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = TelegramNotifier(bot_token="12345:ABCDE", chat_id="998877")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(b"fake_png_data")
            temp_path = tf.name

        try:
            result = await notifier.send_captcha_alert(
                reason="GeeTest слайдер-пазл",
                page_url="https://www.avito.ru/check",
                screenshot_path=temp_path,
                headless=True
            )
            self.assertTrue(result)
            self.assertTrue(mock_post.called)
            call_url = mock_post.call_args.args[0]
            self.assertIn("sendPhoto", call_url)
            data_payload = mock_post.call_args.kwargs.get("data", {})
            self.assertIn("GeeTest слайдер-пазл", data_payload.get("caption", ""))
            self.assertIn("Headless (скрытый)", data_payload.get("caption", ""))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch("httpx.AsyncClient.post")
    async def test_send_captcha_alert_fallback_to_text(self, mock_post):
        """When screenshot is missing, send_captcha_alert falls back to sendMessage."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = TelegramNotifier(bot_token="12345:ABCDE", chat_id="998877")

        result = await notifier.send_captcha_alert(
            reason="Ограничение IP / Доступ заблокирован",
            page_url="https://www.avito.ru/blocked",
            screenshot_path="/non/existent/path.png",
            headless=False
        )
        self.assertTrue(result)
        self.assertTrue(mock_post.called)
        call_url = mock_post.call_args.args[0]
        self.assertIn("sendMessage", call_url)
        json_payload = mock_post.call_args.kwargs.get("json", {})
        self.assertIn("Ограничение IP", json_payload.get("text", ""))
        self.assertIn("Visible (окно Chrome)", json_payload.get("text", ""))


class TestScraperCaptchaHook(unittest.IsolatedAsyncioTestCase):
    async def test_handle_captcha_triggers_notifier_on_ip_block(self):
        """AvitoScraper._handle_captcha must trigger notifier.send_captcha_alert on IP block."""
        config = load_config()
        mock_notifier = MagicMock()
        mock_notifier.send_captcha_alert = AsyncMock(return_value=True)

        scraper = AvitoScraper(config, notifier=mock_notifier)

        mock_page = MagicMock()
        mock_page.title = AsyncMock(return_value="Доступ ограничен: проблема с IP")
        mock_page.url = "https://www.avito.ru/blocked"
        mock_page.screenshot = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock()

        await scraper._handle_captcha(mock_page)

        self.assertTrue(mock_notifier.send_captcha_alert.called)
        call_args = mock_notifier.send_captcha_alert.call_args
        self.assertIn("Ограничение IP", call_args.kwargs.get("reason", ""))
        self.assertEqual(call_args.kwargs.get("page_url"), "https://www.avito.ru/blocked")

    async def test_handle_captcha_triggers_notifier_on_geetest(self):
        """AvitoScraper._handle_captcha must trigger notifier on GeeTest container presence."""
        config = load_config()
        mock_notifier = MagicMock()
        mock_notifier.send_captcha_alert = AsyncMock(return_value=True)

        scraper = AvitoScraper(config, notifier=mock_notifier)

        mock_page = MagicMock()
        mock_page.title = AsyncMock(return_value="Avito Search")
        mock_page.url = "https://www.avito.ru/items"
        mock_page.screenshot = AsyncMock()
        mock_geetest_el = MagicMock()
        mock_page.query_selector = AsyncMock(return_value=mock_geetest_el)
        mock_page.wait_for_timeout = AsyncMock()

        await scraper._handle_captcha(mock_page)

        self.assertTrue(mock_notifier.send_captcha_alert.called)
        call_args = mock_notifier.send_captcha_alert.call_args
        self.assertIn("GeeTest", call_args.kwargs.get("reason", ""))


class TestUniversalSniperIntegration(unittest.TestCase):
    def test_search_target_negation_awareness(self):
        """SearchTarget.quick_filter preserves negated defect phrases and packaging mentions."""
        target = SearchTarget(
            name="RTX 3070",
            query="rtx 3070",
            min_price=20000,
            max_price=35000,
            required_words=["3070"]
        )

        # Legitimate card with negation should pass
        valid_card = {
            "item_id": "val_1",
            "title": "Видеокарта RTX 3070 Gaming (не битая)",
            "raw_description": "Отличное состояние, в комплекте коробка и чек, артефакты отсутствуют",
            "price": 28000
        }
        ok, reason = target.quick_filter(valid_card)
        self.assertTrue(ok, f"Expected valid card to pass, got rejected: {reason}")

        # Defective card must be rejected
        defective_card = {
            "item_id": "def_1",
            "title": "Видеокарта RTX 3070 на запчасти",
            "raw_description": "Была в майнинге, отвал чипа, артефакты по всему экрану",
            "price": 12000
        }
        ok, reason = target.quick_filter(defective_card)
        self.assertFalse(ok)
        self.assertIn("Дефект", reason)

    def test_search_target_gpu_mobile_and_accessories_rejection(self):
        """GPU search rejects mobile chips and coolers."""
        target = SearchTarget(name="RTX 3070", query="rtx 3070")

        # Mobile GPU chip
        mobile_card = {
            "item_id": "mob_1",
            "title": "Видеокарта RTX 3070m 8GB для ноутбука",
            "raw_description": "Мобильный чип 3070m на плате",
            "price": 18000
        }
        ok, reason = target.quick_filter(mobile_card)
        self.assertFalse(ok)
        self.assertIn("Мобильная видеокарта", reason)

        # Cooler only
        cooler_card = {
            "item_id": "cool_1",
            "title": "Кулер для видеокарты RTX 3070",
            "raw_description": "Система охлаждения и вентиляторы для 3070",
            "price": 2500
        }
        ok, reason = target.quick_filter(cooler_card)
        self.assertFalse(ok)
        self.assertIn("Кулер", reason)


class TestRunnerForwarders(unittest.TestCase):
    def test_sniper_ddr4_help_forwarder(self):
        """python sniper_ddr4.py --help delegates to universal_sniper.py."""
        cmd = [sys.executable, "sniper_ddr4.py", "--help"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=os.getcwd())
        self.assertEqual(res.returncode, 0)
        self.assertIn("universal_sniper.py", res.stdout)
        self.assertIn("--preset", res.stdout)

    def test_main_help(self):
        """python main.py --help runs cleanly."""
        cmd = [sys.executable, "main.py", "--help"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=os.getcwd())
        self.assertEqual(res.returncode, 0)
        self.assertIn("Avito RAM AI Sniper Bot", res.stdout)
        self.assertIn("--scan", res.stdout)
        self.assertIn("--loop", res.stdout)


if __name__ == "__main__":
    unittest.main()
