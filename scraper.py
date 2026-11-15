"""
Avito Scraper module.
Uses Playwright with persistent user profile, stealth flags, and resilient selectors.
Supports persistent browser session across multiple scrape cycles.
"""

import asyncio
import logging
import os
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Page, BrowserContext
from config import Config

logger = logging.getLogger(__name__)


def clean_price(price_raw: str) -> Optional[int]:
    """Extracts integer price in rubles from string (e.g. '2 500 ₽' -> 2500)."""
    if not price_raw:
        return None
    cleaned = re.sub(r"[^\d]", "", price_raw)
    try:
        return int(cleaned) if cleaned else None
    except ValueError:
        return None


class AvitoScraper:
    def __init__(self, config: Config):
        self.config = config
        self.profile_dir = os.path.abspath(self.config.user_data_dir)
        os.makedirs(self.profile_dir, exist_ok=True)
        self._pw = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self):
        """Starts a persistent browser context that remains open across scans."""
        if self._context is not None:
            return
        logger.info("Initializing persistent browser session in %s...", self.profile_dir)
        self._pw = await async_playwright().start()
        self._context = await self._create_context(self._pw, headless=self.config.headless)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await self._apply_page_stealth(self._page)
        logger.info("Persistent browser session ready.")

    async def close(self):
        """Closes browser session."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def build_search_url(
        self,
        query: Optional[str] = None,
        sort_by: str = "104",
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        location: Optional[str] = None,
        category: Optional[str] = None
    ) -> str:
        """Constructs search URL with sorting (s=104: newest, s=1: cheapest)."""
        loc = location.strip('/') if location else (self.config.search_location.strip('/') if self.config.search_location else "all")
        
        if category:
            cat = category.strip('/')
            base = f"https://www.avito.ru/{cat}" if cat.startswith("all/") or cat.startswith("rossiya/") else f"https://www.avito.ru/{loc}/{cat}"
        elif category == "":
            base = f"https://www.avito.ru/{loc}"
        elif query:
            base = f"https://www.avito.ru/{loc}"
        else:
            cat = self.config.category_path.strip('/') if self.config.category_path else ""
            if cat.startswith("all/") or cat.startswith("rossiya/"):
                base = f"https://www.avito.ru/{cat}"
            elif cat:
                base = f"https://www.avito.ru/{loc}/{cat}"
            else:
                base = f"https://www.avito.ru/{loc}"
            
        pmin = min_price if min_price is not None else self.config.min_price
        pmax = max_price if max_price is not None else self.config.max_price
        params = {
            "s": str(sort_by),
        }
        if pmin is not None and pmin > 0:
            params["pmin"] = str(pmin)
        if pmax is not None and pmax > 0:
            params["pmax"] = str(pmax)

        effective_query = query if query is not None else self.config.search_query
        if effective_query:
            params["q"] = effective_query
            
        return f"{base}?{urlencode(params)}"

    async def _create_context(self, p, headless: bool) -> BrowserContext:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--lang=ru-RU,ru",
        ]
        
        proxy_dict = None
        if self.config.proxy_url:
            proxy_dict = {"server": self.config.proxy_url}

        context = await p.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            channel="chrome",
            headless=headless,
            viewport={"width": 1366, "height": 850},
            locale="ru-RU",
            proxy=proxy_dict,
            args=args,
            ignore_default_args=["--enable-automation"],
        )
        return context

    async def _apply_page_stealth(self, page: Page):
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

    async def _extract_items_from_page(self, page: Page, max_items: int) -> List[Dict[str, Any]]:
        # Wait for item elements
        await page.wait_for_timeout(2000)
        
        item_elements = await page.query_selector_all('[data-marker="item"]')
        if not item_elements:
            item_elements = await page.query_selector_all('div[data-item-id]')
            
        logger.info("Found %d raw item elements on page.", len(item_elements))
        items: List[Dict[str, Any]] = []
        
        for el in item_elements[:max_items]:
            try:
                # Item ID
                item_id = await el.get_attribute("data-item-id")
                
                # Title and Link
                title_tag = await el.query_selector('[data-marker="item-title"]')
                title = (await title_tag.inner_text()).strip() if title_tag else ""
                
                link_tag = await el.query_selector('a[data-marker="item-title"]') or await el.query_selector('a[itemprop="url"]')
                href = await link_tag.get_attribute("href") if link_tag else ""
                if href and not href.startswith("http"):
                    href = f"https://www.avito.ru{href}"
                    
                if not item_id and href:
                    m = re.search(r"_(\d+)$", href.split("?")[0])
                    item_id = m.group(1) if m else href
                    
                if not item_id or not title:
                    continue
                    
                # Price
                price_tag = await el.query_selector('[data-marker="item-price"]')
                price_text = await price_tag.inner_text() if price_tag else ""
                price = clean_price(price_text)
                
                # Location
                geo_tag = await el.query_selector('[class*="geo-root"], [data-marker="item-address"]')
                location = (await geo_tag.inner_text()).strip() if geo_tag else ""
                
                # Description snippet
                desc_tag = await el.query_selector('[class*="iva-item-description"], [class*="item-description"]')
                snippet = (await desc_tag.inner_text()).strip() if desc_tag else ""
                
                # Image URL
                img_tag = await el.query_selector('img[class*="photo"], img[itemprop="image"], img')
                image_url = await img_tag.get_attribute("src") if img_tag else ""
                
                card_full_text = (await el.inner_text()).lower()
                is_reserved = "зарезервир" in card_full_text or "бронь" in card_full_text or "забронир" in card_full_text

                items.append({
                    "item_id": str(item_id),
                    "title": title,
                    "price": price,
                    "url": href,
                    "location": location,
                    "raw_description": snippet,
                    "image_url": image_url,
                    "is_reserved": is_reserved
                })
            except Exception as item_err:
                logger.debug("Failed to parse single card: %s", item_err)
                continue
                
        return items

    async def _handle_captcha(self, page: Page):
        """Handles challenge or waits for user solution."""
        for _ in range(8):
            title = await page.title()
            if "безопасности" in title.lower() or "получение задания" in title.lower():
                logger.info("Waiting for PoW challenge to complete... (%s)", title)
                await page.wait_for_timeout(1000)
            else:
                break

        current_title = await page.title()
        if "проблема с ip" in current_title.lower() or "доступ ограничен" in current_title.lower():
            logger.warning("Avito captcha challenge encountered!")
            if not self.config.headless:
                print("\n" + "!" * 70)
                print("  [!] ОБНАРУЖЕНА КАПЧА: Передвиньте слайдер в открывшемся окне Chrome!")
                print("  После прохождения сессия сохранится, и дальше капчи не будет.")
                print("!" * 70 + "\n")
                btn = await page.query_selector('button:has-text("Продолжить"), .button-continue, button')
                if btn:
                    try:
                        await btn.click()
                    except Exception:
                        pass
                for _ in range(60):
                    await page.wait_for_timeout(1000)
                    t = await page.title()
                    if "проблема с ip" not in t.lower() and "доступ ограничен" not in t.lower():
                        logger.info("Captcha resolved by user!")
                        await page.wait_for_timeout(2000)
                        break

    async def get_item_full_details(self, item_url: str) -> Dict[str, str]:
        """
        Visits the item page in a background tab to extract full description
        and Avito specification parameters (ECC, Registered, Form Factor, etc.).
        """
        if not item_url or not item_url.startswith("http"):
            return {}
        if not self._context:
            return {}
        
        tab = await self._context.new_page()
        try:
            await tab.goto(item_url, wait_until="domcontentloaded", timeout=20000)
            await tab.wait_for_timeout(1000)
            
            desc_tag = await tab.query_selector('[data-marker="item-view/item-description"], [itemprop="description"]')
            desc = (await desc_tag.inner_text()).strip() if desc_tag else ""
            
            param_tags = await tab.query_selector_all('[data-marker*="item-view/item-params"] li, [class*="params"] li, [data-marker*="item-params"]')
            params = []
            for pt in param_tags:
                try:
                    params.append((await pt.inner_text()).strip())
                except Exception:
                    pass
            params_text = " | ".join(params)
            
            # Check reservation on page
            body_text = (await tab.inner_text("body")).lower()
            is_reserved = any(phrase in body_text for phrase in [
                "товар зарезервирован",
                "зарезервировано",
                "заказ оформлен",
                "товар в резерве",
                "в резерве",
                "объявление снято",
                "снято с публикации",
                "товар продан",
                "объявление закрыто"
            ])
            if not is_reserved:
                res_el = await tab.query_selector('[data-marker*="reserved"], [class*="reserved"], [data-marker="delivery-item-status"], [class*="delivery-status"]')
                if res_el:
                    res_text = (await res_el.inner_text()).lower()
                    if "зарезервир" in res_text or "бронь" in res_text or "оформлен" in res_text:
                        is_reserved = True

            return {
                "full_description": desc,
                "params_text": params_text,
                "is_page_reserved": is_reserved,
                "combined_text": f"{desc}\n{params_text}"
            }
        except Exception as e:
            logger.debug("Failed to fetch full details for %s: %s", item_url, e)
            return {}
        finally:
            try:
                await tab.close()
            except Exception:
                pass

    async def scrape_new_listings(
        self,
        max_items: int = 40,
        query: Optional[str] = None,
        sort_by: str = "104",
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        location: Optional[str] = None,
        category: Optional[str] = None,
        custom_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Scrapes listings from search results."""
        url = custom_url or self.build_search_url(
            query=query,
            sort_by=sort_by,
            min_price=min_price,
            max_price=max_price,
            location=location,
            category=category
        )
        logger.info("Opening Avito URL: %s", url)

        # If persistent context is active, reuse it
        if self._context is not None and self._page is not None:
            try:
                await self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await self._handle_captcha(self._page)
                items = await self._extract_items_from_page(self._page, max_items=max_items)
                logger.info("Extracted %d items using persistent session.", len(items))
                return items
            except Exception as e:
                logger.error("Scraper error in persistent session: %s", e)
                return []

        # Otherwise one-shot execution
        items: List[Dict[str, Any]] = []
        async with async_playwright() as p:
            context = await self._create_context(p, headless=self.config.headless)
            page = context.pages[0] if context.pages else await context.new_page()
            await self._apply_page_stealth(page)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await self._handle_captcha(page)
                items = await self._extract_items_from_page(page, max_items=max_items)
            except Exception as e:
                logger.error("Scraper encountered an error: %s", e)
            finally:
                await context.close()
                
        logger.info("Extracted %d items from Avito (one-shot).", len(items))
        return items
