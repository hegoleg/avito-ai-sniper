"""
Telegram Notifier module.
Formats and dispatches high-priority deal alerts and security/captcha notifications
to user via Telegram Bot API with async support and universal hardware formatting.
Includes fallback logging when Telegram credentials are not yet set.
"""

import asyncio
import logging
import os
import re
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.is_configured = bool(self.bot_token and self.chat_id)

        if not self.is_configured:
            logger.info("TelegramNotifier: No bot_token or chat_id set. Alerts will be printed to terminal.")

    def format_universal_message(self, item: Dict[str, Any], target_name: Optional[str] = None) -> str:
        """
        Formats universal deal card for any hardware category (GPU, CPU, RAM, etc.)
        without hardcoded RAM-only assumptions.
        """
        deal_rating = item.get("deal_rating")
        if deal_rating == "TOP_DEAL":
            header = "🔥 <b>НАХОДКА! СУПЕРЦЕНА НА АВИТО</b>"
        elif deal_rating == "GOOD_DEAL":
            header = "⚡ <b>ВЫГОДНОЕ ПРЕДЛОЖЕНИЕ НА АВИТО</b>"
        else:
            header = "🔥 <b>НАХОДКА! ВЫГОДНАЯ СДЕЛКА НА АВИТО</b>"

        title = item.get("title", "Без названия")
        price = item.get("price")
        price_str = f"<b>{price:,} ₽</b>".replace(",", " ") if price else "Договорная"

        market_price = item.get("estimated_market_price")
        market_str = f" <i>(рынок: ~{market_price:,} ₽)</i>".replace(",", " ") if market_price else ""

        # Hardware-specific specifications block
        if item.get("ram_type") or item.get("capacity_gb"):
            ram_type = item.get("ram_type", "RAM")
            cap = item.get("capacity_gb")
            cap_str = f"{cap} ГБ" if cap else ""
            is_kit = item.get("is_kit", False)
            kit_str = " (комплект)" if is_kit else ""
            freq = item.get("frequency_mhz")
            freq_str = f" @ {freq} МГц" if freq else ""

            form_factor = item.get("form_factor", "DESKTOP_DIMM")
            ff_map = {
                "DESKTOP_DIMM": "🖥 Для ПК (DIMM)",
                "LAPTOP_SODIMM": "💻 Для ноутбука (SO-DIMM)",
                "SERVER_ECC": "⚠️ Серверная (ECC REG)"
            }
            ff_str = ff_map.get(form_factor, "🖥 Память")
            spec_str = f"\n💾 <b>Память:</b> {ram_type} {cap_str}{kit_str}{freq_str}\n⚙️ <b>Тип:</b> {ff_str}"
        elif item.get("specs"):
            spec_str = f"\n⚙️ <b>Характеристики:</b> {item.get('specs')}"
        elif target_name:
            spec_str = f"\n🎯 <b>Цель / Категория:</b> {target_name}"
        else:
            spec_str = ""

        location = item.get("location", "")
        loc_str = f"\n📍 <b>Локация:</b> {location}" if location else ""

        delivery_info = item.get("delivery_info", "")
        deliv_str = f"\n🚚 <b>Доставка:</b> {delivery_info}" if delivery_info else ""

        ai_summary = item.get("ai_summary", "")
        summary_str = f"\n\n🤖 <b>Вердикт ИИ:</b> {ai_summary}" if ai_summary else ""

        red_flags = item.get("red_flags", [])
        flags_str = ""
        if red_flags:
            flags_str = "\n\n⚠️ <b>Предупреждения:</b>\n" + "\n".join(f"• {f}" for f in red_flags)

        url = item.get("url", "https://avito.ru")

        msg = (
            f"{header}\n\n"
            f"📦 <b>{title}</b>\n"
            f"💰 <b>Цена:</b> {price_str}{market_str}"
            f"{spec_str}"
            f"{loc_str}"
            f"{deliv_str}"
            f"{summary_str}"
            f"{flags_str}\n\n"
            f"🔗 <a href=\"{url}\">Открыть на Авито</a>"
        )
        return msg

    def format_message(self, item: Dict[str, Any]) -> str:
        """Legacy compatibility wrapper delegating to format_universal_message."""
        return self.format_universal_message(item)

    async def send_text_message(self, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        """Sends an HTML formatted text message to Telegram."""
        if not self.is_configured:
            print("\n" + "=" * 50)
            print("[УВЕДОМЛЕНИЕ TELEGRAM (Консоль / Без токена)]")
            clean_text = self._strip_html(text)
            print(clean_text)
            print("=" * 50 + "\n")
            return True

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(api_url, json=payload)
                if resp.status_code == 200:
                    logger.info("Successfully sent Telegram message.")
                    return True
                else:
                    logger.error("Failed to send Telegram message: %s - %s", resp.status_code, resp.text)
                    return False
        except Exception as e:
            logger.error("Exception while sending Telegram message: %s", e)
            return False

    async def send_deal_alert(self, item: Dict[str, Any], target_name: Optional[str] = None) -> bool:
        """
        Sends deal notification to Telegram via async httpx, or outputs to console.
        """
        text = self.format_universal_message(item, target_name=target_name)

        if not self.is_configured:
            print("\n" + "=" * 50)
            print("[УВЕДОМЛЕНИЕ О СДЕЛКЕ (Консоль / Без Telegram)]")
            clean_text = self._strip_html(text)
            print(clean_text)
            print("=" * 50 + "\n")
            return True

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        url = item.get("url", "https://avito.ru")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "🚀 Открыть на Авито", "url": url}
                ]]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(api_url, json=payload)
                if resp.status_code == 200:
                    logger.info("Successfully sent deal alert for item %s to Telegram.", item.get("item_id"))
                    return True
                else:
                    logger.error("Failed to send Telegram message: %s - %s", resp.status_code, resp.text)
                    return False
        except Exception as e:
            logger.error("Exception while sending Telegram message: %s", e)
            return False

    def send_deal_alert_sync(self, item: Dict[str, Any], target_name: Optional[str] = None) -> bool:
        """Synchronous version of send_deal_alert for sync CLI scripts."""
        text = self.format_universal_message(item, target_name=target_name)

        if not self.is_configured:
            print("\n" + "=" * 50)
            print("[УВЕДОМЛЕНИЕ О СДЕЛКЕ (Консоль / Без Telegram)]")
            clean_text = self._strip_html(text)
            print(clean_text)
            print("=" * 50 + "\n")
            return True

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        url = item.get("url", "https://avito.ru")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "🚀 Открыть на Авито", "url": url}
                ]]
            }
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(api_url, json=payload)
                if resp.status_code == 200:
                    logger.info("Successfully sent deal alert for item %s to Telegram (sync).", item.get("item_id"))
                    return True
                else:
                    logger.error("Failed to send Telegram message: %s - %s", resp.status_code, resp.text)
                    return False
        except Exception as e:
            logger.error("Exception while sending Telegram message: %s", e)
            return False

    async def send_captcha_alert(
        self,
        reason: str,
        page_url: str,
        screenshot_path: Optional[str] = None,
        headless: bool = True
    ) -> bool:
        """
        Sends an instant security/captcha alert to Telegram.
        Attaches screenshot via sendPhoto API if available, falling back to sendMessage.
        """
        mode_str = "Headless (скрытый)" if headless else "Visible (окно Chrome)"
        text = (
            "🚨 <b>ВНИМАНИЕ: СРАБОТАЛА ЗАЩИТА АВИТО!</b>\n\n"
            f"⚠️ <b>Причина:</b> {reason}\n"
            f"🖥 <b>Режим:</b> {mode_str}\n"
            f"🔗 <b>URL:</b> {page_url}\n\n"
            "🛠 <b>Что делать:</b>\n"
            "Запустите <code>python universal_sniper.py --setup</code> для прохождения проверки в окне браузера."
        )

        if not self.is_configured:
            print("\n" + "!" * 60)
            print("[ТРЕВОГА БЕЗОПАСНОСТИ: КАПЧА / БЛОКИРОВКА АВИТО]")
            clean_text = self._strip_html(text)
            print(clean_text)
            if screenshot_path:
                print(f"[Скриншот сохранён: {screenshot_path}]")
            print("!" * 60 + "\n")
            return True

        # Try sending photo if screenshot file exists
        if screenshot_path and os.path.exists(screenshot_path):
            photo_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    with open(screenshot_path, "rb") as f:
                        files = {"photo": ("captcha_alert.png", f, "image/png")}
                        data = {
                            "chat_id": self.chat_id,
                            "caption": text,
                            "parse_mode": "HTML"
                        }
                        resp = await client.post(photo_url, data=data, files=files)
                        if resp.status_code == 200:
                            logger.info("Successfully sent captcha alert screenshot to Telegram.")
                            return True
                        else:
                            logger.warning(
                                "Failed to send captcha photo (status %s), falling back to text: %s",
                                resp.status_code,
                                resp.text
                            )
            except Exception as e:
                logger.warning("Exception sending captcha photo: %s, falling back to text", e)

        # Fallback to sendMessage
        return await self.send_text_message(text)

    async def test_connection(self) -> bool:
        """Tests Telegram bot token and chat_id asynchronously."""
        if not self.is_configured:
            print("Telegram не настроен (TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заполнены в .env).")
            return False

        test_item = {
            "item_id": "test_999",
            "title": "Тестовое оповещение: GeForce RTX 3070 8GB / DDR4 32GB",
            "price": 28000,
            "estimated_market_price": 35000,
            "specs": "Тестовый прогон Universal Sniper",
            "location": "Москва",
            "deal_rating": "TOP_DEAL",
            "ai_summary": "Связь настроена успешно! Бот готов присылать реальные находки.",
            "url": "https://www.avito.ru"
        }
        return await self.send_deal_alert(test_item, target_name="RTX 3070")

    def test_connection_sync(self) -> bool:
        """Synchronous version of test_connection for CLI commands."""
        if not self.is_configured:
            print("Telegram не настроен (TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заполнены в .env).")
            return False

        test_item = {
            "item_id": "test_999",
            "title": "Тестовое оповещение: GeForce RTX 3070 8GB / DDR4 32GB",
            "price": 28000,
            "estimated_market_price": 35000,
            "specs": "Тестовый прогон Universal Sniper",
            "location": "Москва",
            "deal_rating": "TOP_DEAL",
            "ai_summary": "Связь настроена успешно! Бот готов присылать реальные находки.",
            "url": "https://www.avito.ru"
        }
        return self.send_deal_alert_sync(test_item, target_name="RTX 3070")

    @staticmethod
    def _strip_html(text: str) -> str:
        """Strips HTML tags for clean console display."""
        clean = text.replace("<b>", "").replace("</b>", "")
        clean = clean.replace("<i>", "").replace("</i>", "")
        clean = clean.replace("<code>", "").replace("</code>", "")
        clean = clean.replace('<a href="', " [URL: ").replace('">Открыть на Авито</a>', "]")
        clean = re.sub(r'<[^>]+>', '', clean)
        return clean
