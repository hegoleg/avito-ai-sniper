"""
Telegram Notifier module.
Formats and dispatches high-priority deal alerts to user via Telegram Bot API.
Includes fallback logging when Telegram credentials are not yet set.
"""

import logging
import os
import urllib.parse
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

    def format_message(self, item: Dict[str, Any]) -> str:
        deal_rating = item.get("deal_rating", "GOOD_DEAL")
        if deal_rating == "TOP_DEAL":
            header = "🔥 <b>НАХОДКА! СУПЕРЦЕНА НА АВИТО</b>"
        elif deal_rating == "GOOD_DEAL":
            header = "⚡ <b>ВЫГОДНОЕ ПРЕДЛОЖЕНИЕ НА АВИТО</b>"
        else:
            header = "🔍 <b>НАЙДЕНО НОВОЕ ОБЪЯВЛЕНИЕ</b>"

        title = item.get("title", "Без названия")
        price = item.get("price")
        price_str = f"<b>{price:,} ₽</b>".replace(",", " ") if price else "Договорная"
        
        market_price = item.get("estimated_market_price")
        market_str = f" <i>(рынок: ~{market_price:,} ₽)</i>".replace(",", " ") if market_price else ""
        
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

        location = item.get("location", "")
        loc_str = f"\n📍 <b>Локация:</b> {location}" if location else ""
        
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
            f"💰 <b>Цена:</b> {price_str}{market_str}\n"
            f"💾 <b>Память:</b> {ram_type} {cap_str}{kit_str}{freq_str}\n"
            f"⚙️ <b>Тип:</b> {ff_str}"
            f"{loc_str}"
            f"{summary_str}"
            f"{flags_str}\n\n"
            f"🔗 <a href=\"{url}\">Открыть на Авито</a>"
        )
        return msg

    def send_deal_alert(self, item: Dict[str, Any]) -> bool:
        """Sends a notification to Telegram or outputs to console."""
        text = self.format_message(item)
        
        if not self.is_configured:
            print("\n" + "=" * 50)
            print("[УВЕДОМЛЕНИЕ О СДЕЛКЕ (Консоль / Без Telegram)]")
            # Strip simple html tags for clean terminal print
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace('<a href="', " [URL: ").replace('">Открыть на Авито</a>', "]")
            print(clean_text)
            print("=" * 50 + "\n")
            return True

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "🚀 Открыть на Авито", "url": item.get("url", "https://avito.ru")}
                ]]
            }
        }
        
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(api_url, json=payload)
                if resp.status_code == 200:
                    logger.info("Successfully sent deal alert for item %s to Telegram.", item.get("item_id"))
                    return True
                else:
                    logger.error("Failed to send Telegram message: %s - %s", resp.status_code, resp.text)
                    return False
        except Exception as e:
            logger.error("Exception while sending Telegram message: %s", e)
            return False

    def test_connection(self) -> bool:
        """Tests telegram bot token and chat_id."""
        if not self.is_configured:
            print("Telegram не настроен (TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заполнены).")
            return False
            
        test_item = {
            "item_id": "test_999",
            "title": "Тестовое оповещение: Kingston HyperX DDR4 32GB (2x16) 3200",
            "price": 3500,
            "estimated_market_price": 6200,
            "ram_type": "DDR4",
            "capacity_gb": 32,
            "is_kit": True,
            "frequency_mhz": 3200,
            "form_factor": "DESKTOP_DIMM",
            "location": "Тестовый город",
            "deal_rating": "TOP_DEAL",
            "ai_summary": "Связь настроена успешно! Бот готов присылать реальные находки.",
            "url": "https://www.avito.ru"
        }
        return self.send_deal_alert(test_item)
