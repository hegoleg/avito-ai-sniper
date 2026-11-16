"""
Live RAM Deal Monitor — runs every minute, scrapes Avito, shows good deals.
Displays results in terminal with direct links.
Updated for Oct 2026 memory crisis (prices 2-3x higher).
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

from config import load_config
from database import init_db, is_item_seen, save_listing, get_stats
from scraper import AvitoScraper
from ram_knowledge import evaluate_deal_heuristic, BENCHMARKS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LiveMonitor")

# Suppress noisy playwright logs
logging.getLogger("playwright").setLevel(logging.WARNING)


def analyze_item(title, price, description, location):
    """Analyze using heuristic rules (no API key needed)."""
    return evaluate_deal_heuristic(title, price, description)


def print_deal_card(item, analysis):
    """Print a nice formatted deal card to terminal."""
    rating = analysis.get("deal_rating", "?")
    is_deal = analysis.get("is_deal", False)
    
    # Color / emoji based on rating
    rating_icons = {
        "TOP_DEAL": "🔥🔥🔥",
        "GOOD_DEAL": "⚡⚡",
        "FAIR_PRICE": "🆗",
        "BAD_DEAL": "❌",
        "SUSPICIOUS": "⚠️",
        "NOT_ENOUGH_DATA": "❓",
        "NO_PRICE": "💰❓",
    }
    icon = rating_icons.get(rating, "❓")
    
    title = item.get("title", "?")
    price = item.get("price", "?")
    url = item.get("url", "")
    location = item.get("location", "")
    market_price = analysis.get("estimated_market_price")
    summary = analysis.get("ai_summary", "")
    red_flags = analysis.get("red_flags", [])
    ram_type = analysis.get("ram_type", "?")
    cap = analysis.get("capacity_gb")
    freq = analysis.get("frequency_mhz")
    is_kit = analysis.get("is_kit", False)
    
    if is_deal:
        print()
        print("=" * 70)
        print(f"  {icon} ВЫГОДНОЕ ПРЕДЛОЖЕНИЕ!")
        print("=" * 70)
    else:
        print(f"\n  {icon} [{rating}]", end=" ")
    
    print(f"  📦 {title}")
    price_str = f"{price:,}".replace(",", " ") if isinstance(price, int) else str(price)
    market_str = f" (рынок ~{market_price:,}₽)".replace(",", " ") if market_price else ""
    print(f"  💰 {price_str} ₽{market_str}")
    
    specs = []
    if ram_type and ram_type != "Unknown":
        specs.append(ram_type)
    if cap:
        specs.append(f"{cap}GB")
    if is_kit:
        specs.append("(комплект)")
    if freq:
        specs.append(f"@ {freq}MHz")
    if specs:
        print(f"  💾 {' '.join(specs)}")
    
    if location:
        print(f"  📍 {location}")
    
    if summary:
        print(f"  🤖 {summary}")
    
    if red_flags:
        for flag in red_flags:
            print(f"  ⚠️  {flag}")
    
    if url:
        print(f"  🔗 {url}")
    
    if is_deal:
        print("=" * 70)


async def scan_once(config, scraper, scan_num):
    """Single scan cycle. Returns list of deals found."""
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'─' * 70}")
    print(f"  🔍 СКАНИРОВАНИЕ #{scan_num} | {now}")
    print(f"{'─' * 70}")
    
    try:
        items = await scraper.scrape_new_listings(max_items=40)
    except Exception as e:
        logger.error("Ошибка скрейпинга: %s", e)
        return []
    
    if not items:
        print("  ⏳ Объявлений не получено (защита Авито или нет новых).")
        return []
    
    new_count = 0
    deals = []
    all_analyzed = []
    
    for item in items:
        item_id = item.get("item_id")
        if not item_id:
            continue
            
        # Skip already seen
        if is_item_seen(item_id):
            continue
        
        new_count += 1
        title = item.get("title", "")
        price = item.get("price")
        desc = item.get("raw_description", "")
        location = item.get("location", "")
        
        analysis = analyze_item(title, price, desc, location)
        item.update(analysis)
        
        is_deal = analysis.get("is_deal", False)
        item["notified"] = 0
        
        # Save to DB
        save_listing(item)
        
        all_analyzed.append((item, analysis))
        
        if is_deal:
            deals.append((item, analysis))
    
    # Print summary
    total_on_page = len(items)
    skipped = total_on_page - new_count
    
    print(f"  📊 На странице: {total_on_page} | Новых: {new_count} | Пропущено (уже видели): {skipped}")
    
    if not new_count:
        print("  ✅ Все объявления уже были проанализированы ранее.")
        return []
    
    # Show ALL new items sorted by deal quality
    rating_order = {"TOP_DEAL": 0, "GOOD_DEAL": 1, "FAIR_PRICE": 2, "NOT_ENOUGH_DATA": 3, "BAD_DEAL": 4, "SUSPICIOUS": 5, "NO_PRICE": 6}
    all_analyzed.sort(key=lambda x: rating_order.get(x[1].get("deal_rating", ""), 99))
    
    if deals:
        print(f"\n  🎯 НАЙДЕНО ВЫГОДНЫХ ПРЕДЛОЖЕНИЙ: {len(deals)}!")
        for item, analysis in deals:
            print_deal_card(item, analysis)
    else:
        print(f"\n  😐 Выгодных предложений не найдено в этом цикле.")
    
    # Also show all analyzed for context
    print(f"\n  📋 Все новые объявления ({new_count} шт.):")
    for item, analysis in all_analyzed:
        rating = analysis.get("deal_rating", "?")
        is_deal = analysis.get("is_deal", False)
        icon = "🔥" if rating == "TOP_DEAL" else "⚡" if rating == "GOOD_DEAL" else "🆗" if rating == "FAIR_PRICE" else "❌" if rating == "BAD_DEAL" else "⚠️" if rating == "SUSPICIOUS" else "❓"
        price = item.get("price", "?")
        price_str = f"{price:,}".replace(",", " ") if isinstance(price, int) else str(price)
        market = analysis.get("estimated_market_price")
        market_str = f" (рынок ~{market}₽)" if market else ""
        
        print(f"    {icon} {item.get('title', '?')} — {price_str}₽{market_str}")
        if item.get("url"):
            print(f"       🔗 {item['url']}")
    
    # DB stats
    stats = get_stats()
    print(f"\n  📈 База: {stats['total_seen']} объявлений | {stats['total_deals']} выгодных")
    
    return deals


async def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║        🎯 AVITO AI SNIPER — LIVE MONITOR                       ║")
    print("║        Мониторинг цен на ОЗУ (кризис памяти 2026)              ║")
    print("║        Сканирование каждую минуту | Ctrl+C для остановки        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()
    
    # Show updated benchmarks
    print("📊 Актуальные бенчмарки (кризис памяти, октябрь 2026):")
    for (ram_type, cap, is_kit), (market, good, top) in sorted(BENCHMARKS.items()):
        kit_str = " (kit)" if is_kit else " (1шт)"
        print(f"   {ram_type} {cap}GB{kit_str}: рынок ~{market}₽ | хорошо ≤{good}₽ | супер ≤{top}₽")
    print()
    
    init_db()
    config = load_config()
    scraper = AvitoScraper(config)
    
    scan_num = 0
    total_deals_found = 0
    
    try:
        while True:
            scan_num += 1
            deals = await scan_once(config, scraper, scan_num)
            total_deals_found += len(deals)
            
            if deals:
                print(f"\n  🏆 Всего найдено выгодных за сессию: {total_deals_found}")
            
            print(f"\n  ⏰ Следующее сканирование через 60 секунд... (Ctrl+C для остановки)")
            await asyncio.sleep(60)
            
    except KeyboardInterrupt:
        print(f"\n\n  🛑 Мониторинг остановлен. За сессию найдено выгодных: {total_deals_found}")
        stats = get_stats()
        print(f"  📈 Итого в базе: {stats['total_seen']} объявлений | {stats['total_deals']} выгодных")


if __name__ == "__main__":
    asyncio.run(main())
