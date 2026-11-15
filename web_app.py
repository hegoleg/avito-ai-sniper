"""
FastAPI Web Application: Avito PC Builder & Deal Sniper.
Allows users to configure PC components, set target price ranges,
trigger real-time Avito scraping with anti-bait filters, and track total build savings.
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import load_config
from database import (
    init_db,
    save_listing,
    save_verified_deal,
    mark_deal_reserved_or_inactive,
    get_all_time_top_deals,
    get_connection,
    get_stale_verified_deals,
    update_verified_deal_recheck,
    deactivate_expired_verified_deals,
    cleanup_invalid_verified_deals
)
from scraper import AvitoScraper
from anti_bait import check_listing_bait, check_description_bait
from negation_filter import mask_negations, is_reserved_text
from universal_sniper import SearchTarget, DEFAULT_EXCLUDES, GPU_MOBILE_PATTERNS, GPU_ACCESSORY_PATTERNS
from hardware_catalog import (
    HARDWARE_CATALOG,
    search_catalog,
    get_all_categories,
    get_item_by_id
)
from build_db import (
    init_builder_tables,
    get_current_build,
    select_deal_for_slot,
    clear_slot_selection,
    reset_all_selections,
    update_slot_config,
    apply_build_template,
    BUILD_TEMPLATES
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WebBuilder")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_builder_tables()
    # Expire dead deals from weeks ago and purge bait/invalid records
    purged_expired = deactivate_expired_verified_deals(max_age_days=3)
    purged_invalid = cleanup_invalid_verified_deals()
    logger.info("Startup cleanup: %d expired deals deactivated, %d invalid deals purged.", purged_expired, purged_invalid)
    logger.info("Avito PC Builder Web App started.")
    yield
    global scraper_instance
    if scraper_instance:
        await scraper_instance.close()
        scraper_instance = None
    logger.info("Avito PC Builder Web App stopped.")

app = FastAPI(title="Avito PC Builder & Sniper", lifespan=lifespan)

# Global scraper and scan status
scanner_lock = asyncio.Lock()
scan_state = {
    "is_running": False,
    "slot_id": None,
    "query": "",
    "message": "Готов к работе",
    "progress": 0,
    "new_deals_count": 0,
    "last_error": None
}

scraper_instance: Optional[AvitoScraper] = None


async def get_shared_scraper() -> AvitoScraper:
    global scraper_instance
    if scraper_instance is None:
        cfg = load_config()
        # Web app runs Playwright with persistent session
        scraper_instance = AvitoScraper(cfg)
        await scraper_instance.start()
    return scraper_instance


# Models
class SelectDealRequest(BaseModel):
    slot_id: str
    item_id: str
    title: str
    price: int
    url: str
    location: Optional[str] = ""


class UpdateSlotRequest(BaseModel):
    slot_id: str
    query: str
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    required_words: Optional[str] = ""
    exclude_words: Optional[str] = ""
    retail_est: Optional[int] = None


class ApplyCatalogItemRequest(BaseModel):
    slot_id: str
    catalog_id: str


# Scraper Background Task
async def run_slot_scan(slot_id: str, query: str, min_price: Optional[int], max_price: Optional[int], required: str, exclude: str):
    global scan_state
    async with scanner_lock:
        scan_state["is_running"] = True
        scan_state["slot_id"] = slot_id
        scan_state["query"] = query
        scan_state["message"] = f"Запуск браузера для поиска '{query}'..."
        scan_state["progress"] = 10
        scan_state["new_deals_count"] = 0
        scan_state["last_error"] = None

        try:
            scraper = await get_shared_scraper()
            target = SearchTarget(
                name=query,
                query=query,
                min_price=min_price,
                max_price=max_price,
                location="all",
                required_words=[w.strip() for w in required.split(",") if w.strip()],
                exclude_words=[w.strip() for w in exclude.split(",") if w.strip()]
            )

            # Phase 1: Cheapest
            scan_state["message"] = f"Опрос Авито: самые дешёвые предложения (s=1)..."
            scan_state["progress"] = 25
            items_cheap = await scraper.scrape_new_listings(
                max_items=35,
                query=target.query,
                sort_by="1",
                min_price=target.min_price,
                max_price=target.max_price,
                location="all",
                category=""
            )

            # Phase 2: Newest
            scan_state["message"] = f"Опрос Авито: самые свежие объявления (s=104)..."
            scan_state["progress"] = 50
            items_fresh = await scraper.scrape_new_listings(
                max_items=35,
                query=target.query,
                sort_by="104",
                min_price=target.min_price,
                max_price=target.max_price,
                location="all",
                category=""
            )

            collected = {}
            for it in items_cheap + items_fresh:
                iid = it.get("item_id")
                if iid and iid not in collected:
                    collected[iid] = it

            scan_state["message"] = f"Собрано {len(collected)} объявлений. Фильтрация и проверка..."
            scan_state["progress"] = 70

            candidates = []
            for it in collected.values():
                ok, reason = target.quick_filter(it)
                if ok and it.get("price", 0) > 0:
                    candidates.append(it)
                try:
                    save_listing(it)
                except Exception:
                    pass

            candidates.sort(key=lambda x: x["price"])
            scan_state["message"] = f"Прошло первичный фильтр: {len(candidates)}. Глубокая проверка на бронь и ложные цены..."
            scan_state["progress"] = 80

            verified_count = 0
            for it in candidates[:12]:
                url = it.get("url")
                title = it.get("title")
                price = it.get("price")
                item_id = it.get("item_id")

                details = await scraper.get_item_full_details(url)
                combined_text = details.get("combined_text", "")
                is_page_reserved = details.get("is_page_reserved", False)
                is_closed = details.get("is_closed", False)

                valid, reject_reason = target.verify_full_details(
                    combined_text,
                    is_page_reserved=is_page_reserved,
                    is_closed=is_closed
                )
                if not valid:
                    if item_id:
                        mark_deal_reserved_or_inactive(item_id)
                    continue

                # Calculate savings against slot retail estimate
                retail_est = 0
                try:
                    with get_connection() as conn:
                        s_row = conn.execute("SELECT retail_est FROM pc_build WHERE slot_id = ?", (slot_id,)).fetchone()
                        if s_row and s_row["retail_est"]:
                            retail_est = s_row["retail_est"]
                except Exception:
                    pass

                savings_rub = max(0, retail_est - price) if retail_est and retail_est > price else 0
                savings_pct = round((savings_rub / retail_est) * 100, 1) if retail_est and retail_est > 0 else 0

                deal_entry = {
                    "item_id": str(item_id),
                    "title": title,
                    "price": price,
                    "url": url,
                    "location": it.get("location", ""),
                    "specs": {
                        "query": target.query,
                        "seller_name": details.get("seller_name", ""),
                        "seller_rating": details.get("seller_rating", ""),
                        "seller_reviews": details.get("seller_reviews", ""),
                        "seller_badge": details.get("seller_badge", ""),
                        "has_delivery": details.get("has_delivery", False),
                        "delivery_info": details.get("delivery_info", ""),
                        "retail_est": retail_est,
                        "savings_rub": savings_rub,
                        "savings_pct": savings_pct
                    }
                }
                save_verified_deal(deal_entry, query=target.query)
                verified_count += 1

            scan_state["new_deals_count"] = verified_count
            scan_state["message"] = f"Готово! Подтверждено {verified_count} чистых сделок по '{query}'"
            scan_state["progress"] = 100

        except Exception as e:
            logger.error("Scan error: %s", e, exc_info=True)
            scan_state["last_error"] = str(e)
            scan_state["message"] = f"Ошибка: {e}"
        finally:
            scan_state["is_running"] = False


active_verifying_queries = set()

def format_relative_time(timestamp_str: Optional[str]) -> str:
    """Formats a SQLite timestamp into a friendly human-readable relative string."""
    if not timestamp_str:
        return "недавно"
    try:
        ts_clean = timestamp_str.replace("T", " ").split(".")[0]
        dt = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        diff = now - dt
        total_seconds = int(diff.total_seconds())
        if total_seconds < 0 or total_seconds < 120:
            return "только что"
        if total_seconds < 3600:
            mins = max(1, total_seconds // 60)
            return f"{mins} мин назад"
        if total_seconds < 86400:
            hrs = max(1, total_seconds // 3600)
            return f"{hrs} ч назад"
        days = total_seconds // 86400
        return f"{days} д назад"
    except Exception:
        return "недавно"


async def auto_verify_slot_candidates(query: str):
    """
    Automatic continuous deal maintenance:
    1. Re-validates stale verified deals (> 6 hours old) by visiting live Avito pages.
       Deactivates closed/sold/bait listings immediately.
    2. Checks count of fresh active deals (< 24h). If < 3, auto-scrapes live listings from Avito!
    3. Deeply verifies candidates with Playwright, applying strict desktop/DIMM/non-defect filters.
    100% automated — zero user interaction required.
    """
    clean_q = query.strip().lower()
    if clean_q in active_verifying_queries:
        return
    active_verifying_queries.add(clean_q)

    try:
        scraper = await get_shared_scraper()
        
        # 1. Resolve target and retail_est from pc_build slots
        retail_est = 0
        min_p = None
        max_p = None
        target = None
        with get_connection() as conn:
            s_row = conn.execute(
                "SELECT * FROM pc_build WHERE LOWER(target_query) = ? OR LOWER(target_query) LIKE ? OR slot_id = ?",
                (clean_q, f"%{clean_q}%", clean_q)
            ).fetchone()
            if s_row:
                min_p = s_row["min_price"]
                max_p = s_row["max_price"]
                retail_est = s_row["retail_est"] or 0
                target = SearchTarget(
                    name=s_row["target_query"],
                    query=s_row["target_query"],
                    min_price=min_p,
                    max_price=max_p,
                    required_words=[w.strip() for w in (s_row["required_words"] or "").split(",") if w.strip()],
                    exclude_words=[w.strip() for w in (s_row["exclude_words"] or "").split(",") if w.strip()]
                )

        if not target:
            target = SearchTarget(name=query, query=query, min_price=min_p, max_price=max_p)

        # 2. Re-verify stale deals (> 6 hours old) for this query
        stale_deals = get_stale_verified_deals(max_age_hours=6, query=clean_q, limit=6)
        for sd in stale_deals:
            s_url = sd.get("url")
            s_id = str(sd.get("item_id"))
            if not s_url:
                continue
            try:
                details = await scraper.get_item_full_details(s_url)
                is_closed = details.get("is_closed", False)
                is_page_reserved = details.get("is_page_reserved", False)
                curr_price = details.get("current_price") or sd.get("price")
                combined_text = details.get("combined_text", "")

                # Reject nominal/bait prices on page (e.g. 100 rub)
                if curr_price and curr_price <= 500:
                    is_closed = True

                valid, reason = target.verify_full_details(
                    combined_text,
                    is_page_reserved=is_page_reserved,
                    is_closed=is_closed
                )

                if not valid or is_closed or is_page_reserved:
                    update_verified_deal_recheck(s_id, is_active=False)
                    logger.info("Deal %s closed/invalid on Avito -> deactivated: %s", s_id, reason)
                else:
                    savings_rub = max(0, retail_est - curr_price) if retail_est and retail_est > curr_price else 0
                    savings_pct = round((savings_rub / retail_est) * 100, 1) if retail_est and retail_est > 0 else 0
                    specs_dict = {
                        "query": target.query,
                        "seller_name": details.get("seller_name", ""),
                        "seller_rating": details.get("seller_rating", ""),
                        "seller_reviews": details.get("seller_reviews", ""),
                        "seller_badge": details.get("seller_badge", ""),
                        "has_delivery": details.get("has_delivery", False),
                        "delivery_info": details.get("delivery_info", ""),
                        "retail_est": retail_est,
                        "savings_rub": savings_rub,
                        "savings_pct": savings_pct
                    }
                    update_verified_deal_recheck(s_id, is_active=True, price=curr_price, specs=specs_dict)
                    logger.info("Deal %s re-verified active at %d rub", s_id, curr_price)
            except Exception as ex:
                logger.debug("Error re-checking deal %s: %s", s_id, ex)

        # 3. Check count of fresh verified deals (< 24h)
        with get_connection() as conn:
            fresh_count = conn.execute("""
                SELECT COUNT(*) FROM verified_deals 
                WHERE is_active = 1 
                  AND (LOWER(query) = ? OR LOWER(title) LIKE ?)
                  AND datetime(verified_at) >= datetime('now', '-24 hours')
            """, (clean_q, f"%{clean_q}%")).fetchone()[0]

        # 4. If fewer than 3 fresh deals, auto-scrape fresh listings from Avito
        if fresh_count < 3:
            logger.info("Only %d fresh verified deals for '%s'. Auto-scraping live listings from Avito...", fresh_count, target.query)
            try:
                items_fresh = await scraper.scrape_new_listings(
                    max_items=25,
                    query=target.query,
                    sort_by="104",
                    min_price=target.min_price,
                    max_price=target.max_price,
                    location="all"
                )
                items_cheap = await scraper.scrape_new_listings(
                    max_items=25,
                    query=target.query,
                    sort_by="1",
                    min_price=target.min_price,
                    max_price=target.max_price,
                    location="all"
                )
                for it in items_cheap + items_fresh:
                    iid = it.get("item_id")
                    if iid and it.get("price", 0) > 0:
                        try:
                            save_listing(it)
                        except Exception:
                            pass
            except Exception as ex:
                logger.warning("Auto-scraping error for '%s': %s", target.query, ex)

        # 5. Get candidates from listings not yet in verified_deals
        with get_connection() as conn:
            verified_ids = set(r[0] for r in conn.execute("SELECT item_id FROM verified_deals WHERE is_active = 1").fetchall())
            rows = conn.execute("""
                SELECT item_id, title, price, url, location, raw_description 
                FROM listings 
                WHERE price > 500
                ORDER BY price ASC
            """).fetchall()

        to_inspect = []
        for r in rows:
            iid = str(r["item_id"])
            if iid in verified_ids:
                continue
            if min_p and r["price"] < min_p:
                continue
            if max_p and r["price"] > max_p:
                continue
            ok, _ = target.quick_filter(dict(r))
            if ok:
                to_inspect.append(dict(r))
            if len(to_inspect) >= 6:
                break

        for item in to_inspect:
            url = item.get("url")
            iid = str(item.get("item_id"))
            if not url:
                continue

            details = await scraper.get_item_full_details(url)
            combined_text = details.get("combined_text", "")
            is_page_reserved = details.get("is_page_reserved", False)
            is_closed = details.get("is_closed", False)
            curr_price = details.get("current_price") or item["price"]

            if curr_price and curr_price <= 500:
                is_closed = True

            valid, reason = target.verify_full_details(
                combined_text,
                is_page_reserved=is_page_reserved,
                is_closed=is_closed
            )
            if not valid or is_closed or is_page_reserved:
                mark_deal_reserved_or_inactive(iid)
                with get_connection() as conn:
                    conn.execute("DELETE FROM listings WHERE item_id = ?", (iid,))
                    conn.commit()
                continue

            savings_rub = max(0, retail_est - curr_price) if retail_est and retail_est > curr_price else 0
            savings_pct = round((savings_rub / retail_est) * 100, 1) if retail_est and retail_est > 0 else 0

            specs_dict = {
                "query": target.query,
                "seller_name": details.get("seller_name", ""),
                "seller_rating": details.get("seller_rating", ""),
                "seller_reviews": details.get("seller_reviews", ""),
                "seller_badge": details.get("seller_badge", ""),
                "has_delivery": details.get("has_delivery", False),
                "delivery_info": details.get("delivery_info", ""),
                "retail_est": retail_est,
                "savings_rub": savings_rub,
                "savings_pct": savings_pct
            }

            deal_entry = {
                "item_id": iid,
                "title": item["title"],
                "price": curr_price,
                "url": url,
                "location": item.get("location", ""),
                "specs": specs_dict
            }
            save_verified_deal(deal_entry, query=target.query)
            logger.info("Auto-verified clean deal: %s (%s руб) for %s", item["title"], curr_price, target.query)

    except Exception as e:
        logger.debug("Auto-verifier error for %s: %s", query, e)
    finally:
        active_verifying_queries.discard(clean_q)


# Routes
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = os.path.join(PROJECT_ROOT, "templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Шаблон интерфейса не найден в templates/index.html</h1>"


@app.get("/api/build")
async def get_build_state():
    slots = get_current_build()
    total_build = 0
    total_retail = 0
    filled_slots = 0

    for s in slots:
        if s.get("selected_price"):
            total_build += s["selected_price"]
            filled_slots += 1
        if s.get("retail_est"):
            total_retail += s["retail_est"]

    savings_rub = max(0, total_retail - total_build) if total_build > 0 else 0
    savings_pct = round((savings_rub / total_retail * 100), 1) if total_retail > 0 and total_build > 0 else 0

    return {
        "slots": slots,
        "total_build": total_build,
        "total_retail": total_retail,
        "savings_rub": savings_rub,
        "savings_pct": savings_pct,
        "filled_count": filled_slots,
        "total_slots": len(slots)
    }


@app.post("/api/build/select")
async def select_deal(req: SelectDealRequest):
    select_deal_for_slot(
        slot_id=req.slot_id,
        item_id=req.item_id,
        title=req.title,
        price=req.price,
        url=req.url,
        location=req.location or ""
    )
    return {"status": "ok"}


@app.post("/api/build/clear/{slot_id}")
async def clear_slot(slot_id: str):
    clear_slot_selection(slot_id)
    return {"status": "ok"}


@app.post("/api/build/reset")
async def reset_build():
    reset_all_selections()
    return {"status": "ok"}


@app.post("/api/build/update_slot")
async def update_slot(req: UpdateSlotRequest):
    update_slot_config(
        slot_id=req.slot_id,
        target_query=req.query,
        min_price=req.min_price,
        max_price=req.max_price,
        required_words=req.required_words or "",
        exclude_words=req.exclude_words or "",
        retail_est=req.retail_est
    )
    return {"status": "ok"}


@app.get("/api/catalog/categories")
async def list_catalog_categories():
    """Returns list of component categories."""
    return get_all_categories()


@app.get("/api/catalog")
async def query_catalog(query: str = "", category: Optional[str] = None):
    """Searches hardware chips/components in catalog."""
    items = search_catalog(query=query, category=category, limit=60)
    return {"items": items, "count": len(items)}


@app.get("/api/catalog/{item_id}")
async def get_catalog_item_endpoint(item_id: str):
    """Retrieves single catalog item."""
    it = get_item_by_id(item_id)
    if not it:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    return it


@app.post("/api/build/apply_catalog")
async def apply_catalog_to_slot(req: ApplyCatalogItemRequest):
    """Applies a selected hardware chip from catalog into a PC build slot."""
    item = get_item_by_id(req.catalog_id)
    if not item:
        raise HTTPException(status_code=404, detail="Catalog item not found")

    update_slot_config(
        slot_id=req.slot_id,
        target_query=item["query"],
        min_price=item.get("min_price"),
        max_price=item.get("max_price"),
        required_words=",".join(item.get("required_words", [])),
        exclude_words=",".join(item.get("exclude_words", [])),
        retail_est=item.get("retail_est")
    )
    return {"status": "ok", "applied": item}


@app.post("/api/build/template/{template_id}")
async def apply_template(template_id: str):
    success = apply_build_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "ok"}


@app.get("/api/templates")
async def list_templates():
    return [
        {
            "id": k,
            "title": v["title"],
            "description": v["description"]
        } for k, v in BUILD_TEMPLATES.items()
    ]


def get_smart_top_deals(query: str, min_price: Optional[int] = None, max_price: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
    clean_q = query.strip().lower()
    clean_q_norm = re.sub(r'(\d+)\s*[хx]\b', r'\1x', clean_q)
    
    is_gpu = bool(re.search(r'\b(rtx|gtx|rx|видеокарт|geforce|radeon|gpu)\b', clean_q_norm))
    is_ram = bool(re.search(r'\b(ddr\d?|озу|память|ram)\b', clean_q_norm))

    # Extract primary model tokens (e.g. "5600x", "3070", "b550m", "3200")
    stop_words = {'amd', 'intel', 'nvidia', 'процессор', 'видеокарта', 'для', 'плата', 'материнская', 'память', 'оперативная', 'кулер', 'блок', 'питания', 'корпус', 'со', 'стеклом', 'atx', 'matx'}
    raw_tokens = re.findall(r'[a-zA-Z0-9а-яА-ЯёЁ]+', clean_q_norm)
    key_tokens = [t for t in raw_tokens if t not in stop_words and len(t) > 1]
    if not key_tokens:
        key_tokens = raw_tokens

    results = []
    seen_ids = set()

    with get_connection() as conn:
        # 1. Fetch from verified_deals (only active and fresh within last 3 days)
        verified_rows = conn.execute("""
            SELECT item_id, query, title, price, url, location, specs, verified_at 
            FROM verified_deals 
            WHERE is_active = 1 AND datetime(verified_at) >= datetime('now', '-3 days')
        """).fetchall()
        for v in verified_rows:
            iid = str(v["item_id"])
            p = v["price"]
            if min_price and p < min_price:
                continue
            if max_price and p > max_price:
                continue
                
            t_norm = re.sub(r'(\d+)\s*[хx]\b', r'\1x', v["title"].lower())
            v_query = (v["query"] or "").lower()

            # RAM validation for verified deals
            if is_ram:
                # 1. Laptop / SODIMM
                if re.search(r'\b(sodimm|so-dimm|ноутбук\w*|для\s+ноутбук\w*|ноута|laptop)\b', t_norm):
                    mark_deal_reserved_or_inactive(iid)
                    continue
                # 2. Server RAM
                if re.search(r'\b(ecc|reg|regg|серверн\w*|сервер\b|rdimm|lrdimm|xeon|x99|2011)\b', t_norm):
                    mark_deal_reserved_or_inactive(iid)
                    continue
                # 3. Multi-generation RAM catalog (DDR3 DDR4)
                gens = re.findall(r'\bddr\s*([2-5])\b', t_norm)
                if len(set(gens)) >= 2:
                    mark_deal_reserved_or_inactive(iid)
                    continue
                # 4. Capacity mismatch: if query is 16GB, reject single 8gb
                if any(k in clean_q_norm for k in ["16gb", "16 gb", "16гб"]):
                    if re.search(r'\b8\s*(?:gb|гб)\b', t_norm) and not re.search(r'\b(?:16|32|64)\s*(?:gb|гб)?\b|2\s*[xх*]\s*8', t_norm):
                        mark_deal_reserved_or_inactive(iid)
                        continue
                # 5. Frequency mismatch: if query is 3200, reject lower frequency
                if "3200" in clean_q_norm:
                    if re.search(r'\b(2133|2400|2666)\b', t_norm) and "3200" not in t_norm:
                        mark_deal_reserved_or_inactive(iid)
                        continue

            # GPU validation for verified deals
            if is_gpu:
                if any(re.search(pat, t_norm) for pat in GPU_MOBILE_PATTERNS + GPU_ACCESSORY_PATTERNS):
                    mark_deal_reserved_or_inactive(iid)
                    continue

            # Strict match: all key tokens must be in verified deal title or original query
            if all(k in t_norm or k in v_query for k in key_tokens):
                seen_ids.add(iid)
                specs_obj = {}
                if v["specs"]:
                    try:
                        specs_obj = json.loads(v["specs"])
                    except Exception:
                        pass
                results.append({
                    "item_id": iid,
                    "title": v["title"],
                    "price": p,
                    "url": v["url"],
                    "location": v["location"] or "РФ",
                    "is_verified": True,
                    "verified_at": v["verified_at"],
                    "freshness": format_relative_time(v["verified_at"]),
                    "seller_name": specs_obj.get("seller_name", ""),
                    "seller_rating": specs_obj.get("seller_rating", ""),
                    "seller_reviews": specs_obj.get("seller_reviews", ""),
                    "seller_badge": specs_obj.get("seller_badge", ""),
                    "has_delivery": specs_obj.get("has_delivery", False),
                    "savings_rub": specs_obj.get("savings_rub", 0),
                    "savings_pct": specs_obj.get("savings_pct", 0)
                })

        # 2. Fetch from listings
        listings_rows = conn.execute("""
            SELECT item_id, title, price, url, location, raw_description 
            FROM listings 
            WHERE price > 0
        """).fetchall()

        for r in listings_rows:
            iid = str(r["item_id"])
            if iid in seen_ids:
                continue
            p = r["price"]
            if min_price and p < min_price:
                continue
            if max_price and p > max_price:
                continue

            t_clean = r["title"].lower()
            t_norm = re.sub(r'(\d+)\s*[хx]\b', r'\1x', t_clean)

            # Check all key tokens exist
            if not all(k in t_norm for k in key_tokens):
                continue

            full_text = f"{t_norm} {(r['raw_description'] or '').lower()}"
            if is_reserved_text(full_text):
                continue

            masked_eval = mask_negations(full_text).lower()

            # Defect / trash check (with negation awareness)
            if any(re.search(pat, masked_eval) for pat in DEFAULT_EXCLUDES):
                continue

            # GPU mobile check
            if is_gpu:
                if any(re.search(pat, masked_eval) for pat in GPU_MOBILE_PATTERNS + GPU_ACCESSORY_PATTERNS):
                    continue

            # RAM checks (server / sodimm / laptop)
            if is_ram:
                if any(re.search(pat, full_text) for pat in [
                    r'(?<![а-яА-ЯёЁa-zA-Z])ecc(?![а-яА-ЯёЁa-zA-Z])',
                    r'(?<![а-яА-ЯёЁa-zA-Z])reg(?![а-яА-ЯёЁa-zA-Z])',
                    r'(?<![а-яА-ЯёЁa-zA-Z])сервер',
                    r'(?<![а-яА-ЯёЁa-zA-Z])sodimm',
                    r'(?<![а-яА-ЯёЁa-zA-Z])so-dimm',
                    r'(?<![а-яА-ЯёЁa-zA-Z])ноутбук',
                    r'(?<![а-яА-ЯёЁa-zA-Z])ноута',
                    r'(?<![а-яА-ЯёЁa-zA-Z])x99',
                    r'(?<![а-яА-ЯёЁa-zA-Z])xeon'
                ]):
                    continue

            # Anti-bait check
            is_bait, reason = check_listing_bait(r["title"], r["raw_description"] or "", query=query)
            if is_bait:
                continue

            seen_ids.add(iid)
            results.append({
                "item_id": iid,
                "title": r["title"],
                "price": p,
                "url": r["url"],
                "location": r["location"] or "РФ",
                "is_verified": False
            })

    # Sort: verified deals always first, then by price ascending
    results.sort(key=lambda x: (not x.get("is_verified", False), x["price"]))
    return results[:limit]


@app.get("/api/deals/{query}")
async def get_deals_for_query(query: str, min_price: Optional[int] = None, max_price: Optional[int] = None):
    # Auto-resolve min_price from pc_build slots if not explicitly provided
    if min_price is None:
        try:
            with get_connection() as conn:
                clean_q = query.strip().lower()
                row = conn.execute(
                    "SELECT min_price, max_price FROM pc_build WHERE LOWER(target_query) = ? OR LOWER(target_query) LIKE ? OR slot_id = ?",
                    (clean_q, f"%{clean_q}%", clean_q)
                ).fetchone()
                if row and row["min_price"]:
                    min_price = row["min_price"]
                if row and row["max_price"] and max_price is None:
                    max_price = row["max_price"]
        except Exception:
            pass

    deals = await asyncio.to_thread(
        get_smart_top_deals,
        query=query,
        min_price=min_price,
        max_price=max_price,
        limit=12
    )

    # Automated background maintenance: auto-verify if verified count < 4 OR if deals require re-check
    verified_count = sum(1 for d in deals if d.get("is_verified"))
    has_stale = any(
        d.get("is_verified") and d.get("freshness") not in ["только что", "1 мин назад", "2 мин назад", "5 мин назад"]
        for d in deals
    )
    if verified_count < 4 or has_stale:
        asyncio.create_task(auto_verify_slot_candidates(query))

    return {"deals": deals, "total": len(deals), "verified_count": verified_count}


@app.post("/api/scan/{slot_id}")
async def trigger_scan(slot_id: str, background_tasks: BackgroundTasks):
    global scan_state
    if scan_state["is_running"]:
        return JSONResponse(status_code=409, content={"status": "busy", "message": "Сканирование уже выполняется"})

    slots = get_current_build()
    slot = next((s for s in slots if s["slot_id"] == slot_id), None)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    # Prevent rapid double-click race conditions
    scan_state["is_running"] = True
    scan_state["slot_id"] = slot_id
    scan_state["query"] = slot["target_query"]
    scan_state["message"] = f"Подготовка к поиску '{slot['target_query']}'..."
    scan_state["progress"] = 5
    scan_state["new_deals_count"] = 0
    scan_state["last_error"] = None

    background_tasks.add_task(
        run_slot_scan,
        slot_id=slot["slot_id"],
        query=slot["target_query"],
        min_price=slot.get("min_price"),
        max_price=slot.get("max_price"),
        required=slot.get("required_words", ""),
        exclude=slot.get("exclude_words", "")
    )
    return {"status": "started", "slot_id": slot_id, "query": slot["target_query"]}


@app.get("/api/scan/status")
async def get_scan_status():
    return scan_state


if __name__ == "__main__":
    import uvicorn
    print("\n" + "═" * 70)
    print("  🚀 ЗАПУСК ВЕБ-ПРИЛОЖЕНИЯ 'AVITO PC BUILDER'")
    print("  🌐 Откройте в браузере: http://127.0.0.1:8000  или  http://localhost:8000")
    print("═" * 70 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
