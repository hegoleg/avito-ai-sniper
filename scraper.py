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
from negation_filter import is_reserved_text

logger = logging.getLogger(__name__)


def clean_price(price_raw: str) -> Optional[int]:
    """
    Extracts integer price in rubles from string, safely handling:
    - Strike-through / old prices (e.g. '2 500 ₽ 3 000 ₽' -> 2500)
    - Discount badges and percentages (e.g. '2 500 ₽ -17% 3 000 ₽' -> 2500)
    - Multiline price blocks (e.g. '2 500 ₽\\n3 000 ₽' -> 2500)
    - Plain numbers without currency (e.g. '15000' -> 15000)
    - Ranges and prefix text (e.g. 'от 4 500 ₽' -> 4500)
    """
    if not price_raw or not isinstance(price_raw, str):
        return None

    # 1. If multiline, evaluate the first non-empty line
    lines = [line.strip() for line in price_raw.splitlines() if line.strip()]
    first_line = lines[0] if lines else price_raw

    # Strip percentage tokens (e.g. -17%, +5%)
    first_line_clean = re.sub(r"[-+]?\d+%", "", first_line)

    # Strip decimal kopecks (e.g. ,00 or .00 or ,50) before currency symbol or end of string
    first_line_clean = re.sub(r"[,.]\d{2}(?=\s*(?:₽|руб|р\b|$))", "", first_line_clean)

    # 2. Extract first price token associated with ruble currency symbol
    curr_pat = r"(\d{1,3}(?:[\s\xa0]\d{3})+|\d+)\s*(?:₽|руб(?:лей|\.?)?|р\b)"
    currency_match = re.search(curr_pat, first_line_clean, re.IGNORECASE)
    if currency_match:
        digits = re.sub(r"[^\d]", "", currency_match.group(1))
        if digits:
            try:
                return int(digits)
            except ValueError:
                pass

    # 3. Fallback: first currency match in full text
    full_clean = re.sub(r"[-+]?\d+%", "", price_raw)
    full_clean = re.sub(r"[,.]\d{2}(?=\s*(?:₽|руб|р\b|$))", "", full_clean)
    currency_match_full = re.search(curr_pat, full_clean, re.IGNORECASE)
    if currency_match_full:
        digits = re.sub(r"[^\d]", "", currency_match_full.group(1))
        if digits:
            try:
                return int(digits)
            except ValueError:
                pass

    # 4. Fallback: extract first standalone number sequence
    num_pat = r"(\d{1,3}(?:[\s\xa0]\d{3})+|\d+)"
    num_match = re.search(num_pat, first_line_clean)
    if num_match:
        digits = re.sub(r"[^\d]", "", num_match.group(1))
        if digits:
            try:
                return int(digits)
            except ValueError:
                pass

    return None


class AvitoScraper:
    def __init__(self, config: Config, notifier: Optional[Any] = None):
        self.config = config
        self.notifier = notifier
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
                    
                # Price extraction: check Schema.org meta first, then fallback to active item-price marker
                price = None
                meta_price = await el.query_selector('meta[itemprop="price"]')
                if meta_price:
                    meta_content = await meta_price.get_attribute("content")
                    if meta_content:
                        price = clean_price(meta_content)

                if price is None:
                    # Target active price element specifically, avoiding old-price tags
                    price_tag = await el.query_selector(
                        '[data-marker="item-price"] strong, '
                        '[data-marker="item-price"] [class*="price-value"], '
                        '[data-marker="item-price"]'
                    )
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
                
                card_full_text = await el.inner_text()
                is_reserved = is_reserved_text(card_full_text)

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

        current_title = (await page.title()).lower()
        is_ip_block = "проблема с ip" in current_title or "доступ ограничен" in current_title
        geetest_el = await page.query_selector('[class*="geetest"], .button-continue, button:has-text("Продолжить")')
        is_challenge = is_ip_block or bool(geetest_el)

        if is_challenge:
            reason = "GeeTest слайдер-пазл" if geetest_el else "Ограничение IP / Доступ заблокирован"
            logger.warning("Avito captcha challenge encountered: %s (Title: %s)", reason, current_title)

            # Capture screenshot for alert
            screenshot_path = os.path.join(self.profile_dir, "captcha_alert.png")
            try:
                await page.screenshot(path=screenshot_path)
            except Exception as ss_err:
                logger.debug("Could not take captcha screenshot: %s", ss_err)
                screenshot_path = None

            # Trigger captcha alert if notifier is configured
            if self.notifier:
                try:
                    await self.notifier.send_captcha_alert(
                        reason=reason,
                        page_url=page.url,
                        screenshot_path=screenshot_path,
                        headless=self.config.headless
                    )
                except Exception as notif_err:
                    logger.error("Failed to send captcha alert via notifier: %s", notif_err)

            if not self.config.headless:
                print("\n" + "!" * 70)
                print(f"  [!] ОБНАРУЖЕНА КАПЧА ({reason}): Передвиньте слайдер в открывшемся окне Chrome!")
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
                    t = (await page.title()).lower()
                    if "проблема с ip" not in t and "доступ ограничен" not in t:
                        logger.info("Captcha resolved by user!")
                        await page.wait_for_timeout(2000)
                        break

    async def get_item_full_details(self, item_url: str) -> Dict[str, Any]:
        """
        Visits the item page in a background tab to extract full description,
        Avito specification parameters, reservation status, delivery options,
        and seller information. Scoped strictly to item blocks, avoiding
        false positives from recommendation carousels.
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
            
            # Localized status checks strictly scoped to the listing action / delivery block
            # (Completely excludes recommendation blocks and similar items carousels)
            is_reserved = False
            is_closed = False
            has_delivery = False
            delivery_info = ""
            seller_name = ""
            seller_rating = ""

            # 1. Price extraction on item page
            current_price = None
            meta_price = await tab.query_selector('meta[itemprop="price"]')
            if meta_price:
                m_content = await meta_price.get_attribute("content")
                if m_content:
                    current_price = clean_price(m_content)

            if current_price is None:
                price_tag = await tab.query_selector(
                    '[data-marker="item-view/item-price"] strong, '
                    '[data-marker="item-view/item-price"] [class*="price-value"], '
                    '[data-marker="item-view/item-price"], '
                    '[itemprop="price"], '
                    '[class*="style-price-value-main"]'
                )
                if price_tag:
                    price_text = await price_tag.inner_text()
                    current_price = clean_price(price_text)

            # 2. Check for closed/archived listing banner strictly within main container or page alerts
            main_container = await tab.query_selector('[data-marker="item-view"], main') or tab
            closed_el = await main_container.query_selector(
                '[data-marker="item-view/closed-warning"], [data-marker="closed-item-warning"], '
                '[data-marker*="closed"], [class*="closed-warning"], [class*="closedWarning"], [class*="item-closed"], '
                'div:has-text("снято с публикации"), p:has-text("снято с публикации"), span:has-text("снято с публикации"), '
                'div:has-text("Объявление закрыто"), div:has-text("Товар продан")'
            )
            if closed_el:
                closed_text = (await closed_el.inner_text()).lower()
                if any(p in closed_text for p in ["закрыто", "снято с публикации", "товар продан"]):
                    is_closed = True
                    is_reserved = True

            # 3. Direct reservation check (e.g. disabled 'Товар зарезервирован' button or status badge)
            reserved_els = await tab.query_selector_all(
                'button:has-text("зарезервирован"), '
                'div:has-text("Товар зарезервирован"), '
                'span:has-text("Товар зарезервирован"), '
                'p:has-text("Товар зарезервирован"), '
                '[data-marker*="delivery-item-status"]:has-text("зарезервирован"), '
                '[data-marker*="reserved"], '
                '[class*="reserved"], '
                '[class*="item-reserved"]'
            )
            for r_el in reserved_els:
                # Exclude recommendation carousels
                is_in_rec = await r_el.evaluate(
                    'el => Boolean(el.closest("[data-marker*=\\"recommendation\\"], [class*=\\"recommendation\\"], [class*=\\"carousel\\"], [data-marker*=\\"carousel\\"], [class*=\\"item-view-recommendations\\"]"))'
                )
                if not is_in_rec:
                    r_text = (await r_el.inner_text()).lower()
                    if "зарезервирован" in r_text or is_reserved_text(r_text):
                        is_reserved = True
                        break

            # 4. Scope reservation & delivery to aside container
            aside_block = await tab.query_selector('aside, [data-marker="item-view/aside"], [class*="item-view-aside"]')
            if aside_block and not is_reserved:
                aside_text = (await aside_block.inner_text()).lower()
                if is_reserved_text(aside_text):
                    is_reserved = True

            action_block = await tab.query_selector(
                '[data-marker="item-view/actions"], '
                '[class*="style-item-price-and-actions"], '
                '[class*="style-item-view-aside"], '
                '[class*="item-view-actions"], '
                '[data-marker="item-view/aside"], '
                'aside'
            )

            # Fallback: check if buy/contact buttons are replaced with "Оценить продавца" (closed indicator)
            if not is_closed and action_block:
                eval_seller_btn = await action_block.query_selector('button:has-text("Оценить продавца"), a:has-text("Оценить продавца")')
                contact_btn = await action_block.query_selector(
                    'button[data-marker*="phone"], button[data-marker*="messenger"], button[data-marker*="delivery"]'
                )
                if eval_seller_btn and not contact_btn:
                    is_closed = True
                    is_reserved = True
            delivery_block = None
            if action_block:
                delivery_block = await action_block.query_selector(
                    '[data-marker="delivery-item-status"], [data-marker="delivery-block"], [data-marker="item-view/delivery"], [class*="delivery-block"]'
                )
            if not delivery_block:
                delivery_block = await tab.query_selector(
                    '[data-marker="item-view"] [data-marker="delivery-item-status"], [data-marker="item-view"] [class*="delivery-block"]'
                )

            if delivery_block:
                delivery_info = (await delivery_block.inner_text()).strip()
                del_lower = delivery_info.lower()
                if is_reserved_text(del_lower):
                    is_reserved = True
                if "доставка" in del_lower and "недоступна" not in del_lower:
                    has_delivery = True

            if action_block and not is_reserved:
                action_text = (await action_block.inner_text()).lower()
                if is_reserved_text(action_text):
                    is_reserved = True
                
                # Check delivery button
                delivery_btn = await action_block.query_selector(
                    'button[data-marker*="delivery"], [data-marker*="delivery-button"]'
                )
                if delivery_btn:
                    has_delivery = True

            # 3. Extract seller details (name, rating, reviews count, verification badge)
            seller_rating = ""
            seller_reviews = ""
            seller_badge = ""

            seller_name_el = await tab.query_selector(
                '[data-marker="seller-info/name"], [data-marker="seller-info/label"], [class*="seller-info-name"]'
            )
            if seller_name_el:
                seller_name = (await seller_name_el.inner_text()).strip()

            seller_rating_el = await tab.query_selector(
                '[data-marker="seller-info/rating"], [data-marker="seller-rating/score"], [data-marker*="seller-rating"], [class*="seller-rating"]'
            )
            if seller_rating_el:
                rating_raw = (await seller_rating_el.inner_text()).strip()
                m_score = re.search(r"(\d+[,.]\d+)", rating_raw)
                if m_score:
                    seller_rating = m_score.group(1).replace(",", ".")
                m_rev = re.search(r"(\d+[\s\d]*\s*отзыв\w*)", rating_raw, re.IGNORECASE)
                if m_rev:
                    seller_reviews = m_rev.group(1).strip()

            badge_el = await tab.query_selector(
                '[data-marker*="seller-badge"], [class*="seller-badge"], span:has-text("подтверждены"), span:has-text("проверены")'
            )
            if badge_el:
                seller_badge = (await badge_el.inner_text()).strip()

            return {
                "full_description": desc,
                "params_text": params_text,
                "current_price": current_price,
                "is_page_reserved": is_reserved,
                "is_closed": is_closed,
                "has_delivery": has_delivery,
                "delivery_info": delivery_info,
                "seller_name": seller_name,
                "seller_rating": seller_rating,
                "seller_reviews": seller_reviews,
                "seller_badge": seller_badge,
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
