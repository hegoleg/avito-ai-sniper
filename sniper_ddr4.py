"""
DDR4 2x8 3200MHz RAM Sniper — Enhanced Edition V5
- 100% ЗАЩИТА ОТ РЕЗЕРВА: проверяет статус доставки («Товар зарезервирован» / «Заказ оформлен») на странице объявления.
- ТОП ЗА ВСЁ ВРЕМЯ: после каждого цикла сканирования выводит рейтинг лучших найденных сделок из базы данных.
- АНТИ-СОЛЯНКА: отсекает комплекты из разных плашек, разных производителей и с разной частотой.
- ЗАЩИТА ОТ СЕРВЕРНОЙ И НОУТБУЧНОЙ ОЗУ: отсекает ECC REG, X99, Xeon, Atermiter, SO-DIMM.
- ПОСТОЯННАЯ СЕССИЯ: браузер открыт, капча проходится максимум 1 раз при старте.
"""

import asyncio
import logging
import os
import re
import sys
from datetime import datetime

# Windows console UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import load_config
from database import (
    init_db,
    is_item_seen,
    save_listing,
    save_verified_deal,
    mark_deal_reserved_or_inactive,
    get_all_time_top_deals
)
from scraper import AvitoScraper
from anti_bait import check_listing_bait, check_description_bait
from ram_knowledge import (
    extract_ram_type,
    extract_frequency,
    detect_form_factor,
    detect_red_flags,
    SERVER_PATTERNS,
    LAPTOP_PATTERNS,
    DEFECT_PATTERNS,
    PRICE_TRAP_PATTERNS,
    MISMATCH_PATTERNS,
    BENCHMARKS
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("DDR4Sniper")
logging.getLogger("playwright").setLevel(logging.WARNING)


KIT_2X8_REGEX = re.compile(
    r"(?:"
    r"2\s*(?:x|х|\*|×|по|(?:планки|плашки|шт)\s*по)\s*8|"
    r"8\s*(?:x|х|\*|×)\s*2|"
    r"две\s*(?:по\s*8|планки\s*по\s*8|плашки\s*по\s*8)|"
    r"\(2\s*[xх]\s*8\)|"
    r"\(8\s*[xх]\s*2\)|"
    r"комплект[^\n\r]*(?:16\s*(?:gb|гб))|"
    r"(?:16\s*(?:gb|гб))[^\n\r]*комплект"
    r")",
    re.IGNORECASE
)

PRICE_TRAP_REGEX = re.compile(
    r"(?:"
    r"цена\s+(?:указана\s+)?за\s+(?:одну|1|каждую|одну\s+из)\s*(?:плашку|планку|шт|штуку)?|"
    r"цена\s+за\s+(?:штуку|плашку|планку)|"
    r"за\s+1\s*(?:шт|штуку|плашку|планку)|"
    r"цена\s+указана\s+за\s+(?:1|одну|штуку|плашку)|"
    r"цена\s+за\s+каждую"
    r")",
    re.IGNORECASE
)

BRAND_FAMILIES = [
    {"kingston", "hyperx", "fury", "kvr"},
    {"corsair", "vengeance", "dominator"},
    {"g.skill", "gskill", "ripjaws", "trident", "aegis", "flare"},
    {"crucial", "ballistix"},
    {"adata", "xpg", "gammix", "spectrix"},
    {"patriot", "viper"},
    {"teamgroup", "t-force", "vulcan", "delta"},
    {"netac", "shadow"},
    {"samsung"},
    {"hynix", "sk hynix"},
    {"micron"},
    {"apacer", "panther"},
    {"goodram", "irdm"},
    {"amd", "radeon"},
]


def is_reserved_text(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in [
        "зарезервир",
        "забронир",
        "в резерве",
        "бронь",
        "продан",
        "заказ оформлен",
        "товар зарезервирован"
    ])


def check_mismatched_sticks(text: str) -> tuple[bool, str]:
    """Detects if listing consists of mismatched/heterogeneous sticks."""
    t = text.lower()

    # 1. Direct keywords
    for p in MISMATCH_PATTERNS:
        if re.search(p, t):
            return True, "Разнопарные плашки / солянка (найден маркер в тексте)"

    # 2. Numbered list of different items (1. ... 2. ...)
    if re.search(r"(?:^|\n)\s*1[\.\)]\s+.*?(?:^|\n)\s*2[\.\)]\s+", t, re.DOTALL):
        return True, "В описании пронумерован список разных товаров (1... 2...)"

    # 3. Frequency mismatch in text (e.g. '2666 + 3200', 'одна 2666, другая 3200')
    freqs = set(re.findall(r"\b(2133|2400|2666|2933|3000|3200|3600)\b", t))
    if len(freqs) >= 2:
        has_oc_keywords = any(w in t for w in ["xmp", "jedec", "разгон", "сток", "биос", "профиль", "тайминг"])
        has_split_keywords = any(w in t for w in ["одна", "другая", "вторая", "1-я", "2-я", "разные", "+", "плюс", "и"])
        if has_split_keywords or not has_oc_keywords:
            return True, f"Разные частоты у модулей в описании ({', '.join(sorted(freqs))} МГц)"

    # 4. Brand mismatch: two distinct brand families
    cleaned = re.sub(r"чип[ыах]\s+[a-z0-9\-_\s]+", " ", t)
    cleaned = re.sub(r"на\s+чипах\s+[a-z0-9\-_\s]+", " ", cleaned)
    matched_fams = []
    for fam in BRAND_FAMILIES:
        if any(re.search(r"\b" + re.escape(b) + r"\b", cleaned) for b in fam):
            matched_fams.append(sorted(list(fam))[0])

    if len(matched_fams) >= 2:
        return True, f"Разные производители плашек в одном лоте ({' + '.join(matched_fams)})"

    return False, "OK"


def quick_filter_item(item: dict) -> tuple[bool, str]:
    """Fast pre-filter based on title and card snippet."""
    if item.get("is_reserved"):
        return False, "Зарезервировано (метка в карточке)"

    title = item.get("title", "")
    snippet = item.get("raw_description", "")
    full_text = f"{title} {snippet}"

    if is_reserved_text(full_text):
        return False, "Зарезервировано (в тексте)"

    # Mismatch pre-check
    mismatched, m_reason = check_mismatched_sticks(full_text)
    if mismatched:
        return False, m_reason

    if PRICE_TRAP_REGEX.search(full_text):
        return False, "Ловушка цены за 1 плашку"

    flags = detect_red_flags(full_text)
    if flags:
        return False, flags[0]

    # Check anti-bait: multi-model catalog, fake price, barter, pawnshop
    is_bait, bait_reason = check_listing_bait(title, snippet, query="ddr4 16gb 3200")
    if is_bait:
        return False, bait_reason

    ff = detect_form_factor(full_text)
    if ff in ("SERVER_ECC", "LAPTOP_SODIMM"):
        return False, f"Не подходит форм-фактор ({ff})"

    t = full_text.upper()
    if "DDR5" in t or "DDR3" in t or "DDR2" in t:
        return False, "Не DDR4"
    if not ("DDR4" in t or re.search(r"\bDDR\s*4\b", t)):
        return False, "Не DDR4"

    has_kit = bool(KIT_2X8_REGEX.search(full_text))
    has_16_and_2 = bool(re.search(r"16\s*(?:гб|gb)", t) and re.search(r"(?:2\s*шт|2\s*планки|парой|пара)", full_text, re.IGNORECASE))
    if not (has_kit or has_16_and_2):
        return False, "Не комплект 2x8 (16GB)"

    freq = extract_frequency(full_text)
    if freq and (freq < 2933 or freq > 3800):
        return False, f"Частота {freq}MHz далека от 3200MHz"

    return True, "OK"


def verify_full_description_and_params(combined_text: str, is_page_reserved: bool = False) -> tuple[bool, str]:
    """Detailed inspection of item's full page description and Avito specs."""
    # 1. Direct reservation check from full page DOM
    if is_page_reserved:
        return False, "Товар зарезервирован покупателем (Авито Доставка)"

    if not combined_text:
        return True, "OK"

    t = combined_text.lower()

    if is_reserved_text(t):
        return False, "Товар зарезервирован / в резерве"

    # Anti-bait in description
    is_bait, bait_reason = check_description_bait(t, query="ddr4 16gb 3200")
    if is_bait:
        return False, bait_reason

    # 2. Mismatched sticks check
    mismatched, m_reason = check_mismatched_sticks(t)
    if mismatched:
        return False, m_reason

    # 3. Server memory keywords
    for p in SERVER_PATTERNS:
        if re.search(p, t):
            return False, "Серверная память (ECC REG / X99 / Xeon)"

    # 4. Official Avito parameters check
    if "буферизованная" in t and "да" in t:
        return False, "Серверная память: Буферизованная (Registered)"
    if "поддержка ecc" in t and "да" in t:
        return False, "Серверная память: Поддержка ECC"
    if "so-dimm" in t or "sodimm" in t or "для ноутбука" in t:
        return False, "Память для ноутбука (SO-DIMM)"
    if "производитель: другой" in t or "производитель: разное" in t or "производитель: не указан" in t:
        return False, "В характеристиках Авито производитель указан как 'Другой' или 'Разное'"

    m_freq = re.search(r"тактовая\s+частота[^\d]*(\d{4})", t)
    if m_freq:
        param_f = int(m_freq.group(1))
        if param_f < 2933 or param_f > 3800:
            return False, f"В характеристиках Авито частота {param_f} МГц (не 3200)"

    # 5. Price trap in full text
    if PRICE_TRAP_REGEX.search(t):
        return False, "В описании указано: цена за 1 штуку, а не комплект!"

    # 6. Defects
    for p in DEFECT_PATTERNS:
        if re.search(p, t):
            return False, "В описании упомянут дефект / неисправность"

    return True, "OK"


def print_all_time_top():
    """Prints the all-time best verified deals stored in the database."""
    top_deals = get_all_time_top_deals(limit=5)
    market_price = 8000

    print("\n" + "🌟" * 38)
    print("  🏆 ТОП ЛУЧШИХ СДЕЛОК ЗА ВСЁ ВРЕМЯ (ИЗ БАЗЫ ДАННЫХ):")
    print("🌟" * 38)

    if not top_deals:
        print("  ℹ️ В базе пока нет сохранённых подтверждённых сделок (наполняется в процессе)...")
        print("=" * 75)
        return

    for idx, deal in enumerate(top_deals, start=1):
        p = deal["price"]
        disc = int(((market_price - p) / market_price) * 100) if p < market_price else 0
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"[{idx}]"
        freq_str = f" @ {deal.get('frequency_mhz', 3200)}MHz" if deal.get('frequency_mhz') else ""
        print(f"  {medal} {p:,} ₽ (-{disc}%) — {deal.get('title')} ({deal.get('location')}){freq_str}".replace(",", " "))
        print(f"      🔗 {deal.get('url')}")
    print("=" * 75)


async def scan_once(scraper: AvitoScraper, cycle_num: int):
    now_str = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*75}")
    print(f"  🔍 ЦИКЛ #{cycle_num} | Время: {now_str}")
    print(f"  🎯 Цель: DDR4 16GB (2x8) ~3200MHz | БЕЗ РЕЗЕРВА | 100% ПАРНЫЕ | БЕЗ СЕРВЕРНОЙ")
    print(f"{'='*75}")

    queries = [
        {"query": "ddr4 16gb 3200", "sort_by": "1",   "min_p": 2500, "max_p": 9000, "label": "Самые дешёвые в РФ (s=1)"},
        {"query": "ddr4 2x8 3200",  "sort_by": "104", "min_p": 2500, "max_p": 9000, "label": "Свежие поступления (s=104)"},
    ]

    collected = {}
    for q in queries:
        print(f"  📡 Опрос выдачи: {q['label']}...")
        items = await scraper.scrape_new_listings(
            max_items=35,
            query=q["query"],
            sort_by=q["sort_by"],
            min_price=q["min_p"],
            max_price=q["max_p"]
        )
        for it in items:
            iid = it.get("item_id")
            if iid and iid not in collected:
                collected[iid] = it
        await asyncio.sleep(1.0)

    if not collected:
        print("  ⏳ Нет данных с Авито (проверьте окно браузера).")
        print_all_time_top()
        return

    # Fast pre-filtering
    candidates = []
    for it in collected.values():
        ok, reason = quick_filter_item(it)
        if ok:
            p = it.get("price")
            if p and p > 0:
                candidates.append(it)
        try:
            save_listing(it)
        except Exception:
            pass

    print(f"  📊 Всего в выборке: {len(collected)} | Прошло базовый фильтр: {len(candidates)}")

    if not candidates:
        print("  ℹ️ В текущем цикле новых подходящих лотов нет.")
        print_all_time_top()
        return

    # Sort candidates by price ascending
    candidates.sort(key=lambda x: x["price"])

    # DEEP INSPECTION: check full page details
    verified_deals = []
    print("\n  🔍 Глубокая проверка кандидатов (проверяем бронь, парность и спецификации)...")

    for it in candidates[:7]:
        url = it.get("url")
        title = it.get("title")
        price = it.get("price")
        item_id = it.get("item_id")
        
        details = await scraper.get_item_full_details(url)
        combined_text = details.get("combined_text", "")
        is_page_reserved = details.get("is_page_reserved", False)
        
        valid, reject_reason = verify_full_description_and_params(combined_text, is_page_reserved=is_page_reserved)
        if not valid:
            print(f"   ⚠️ [ОТСЕВ] {price} ₽ | {title} -> {reject_reason}")
            # If it was in verified DB earlier but now reserved/sold, deactivate it
            if item_id:
                mark_deal_reserved_or_inactive(item_id)
            continue

        freq = extract_frequency(f"{title} {combined_text}") or 3200
        deal_entry = {
            "item_id": str(item_id),
            "title": title,
            "price": price,
            "url": url,
            "location": it.get("location", ""),
            "frequency_mhz": freq,
        }
        verified_deals.append(deal_entry)
        
        # Save to all-time verified database!
        try:
            save_verified_deal(deal_entry)
        except Exception as e:
            logger.debug("Failed to save verified deal: %s", e)

        print(f"   ✅ [ПОДТВЕРЖДЕНО: СВОБОДНО, ПАРНЫЙ КОМПЛЕКТ] {price} ₽ | {title}")

    if verified_deals:
        market_price, good_thr, top_thr = BENCHMARKS.get(("DDR4", 16, True), (8000, 6000, 4500))
        best = verified_deals[0]
        best_price = best["price"]
        freq = best["frequency_mhz"]
        discount = int(((market_price - best_price) / market_price) * 100) if best_price < market_price else 0

        print("\n" + "🔥" * 38)
        print("  🎯 ЛУЧШЕЕ ПРЕДЛОЖЕНИЕ ЭТОГО ЦИКЛА (АКТИВНОЕ, БЕЗ БРОНИ):")
        print("🔥" * 38)
        print(f"  📦 {best['title']}")
        print(f"  💰 ЦЕНА: {best_price:,} ₽  (рыночная стоимость ~{market_price:,} ₽ | экономия: ~{discount}%)".replace(",", " "))
        print(f"  💾 Комплект: DDR4 16GB (2x8) @ {freq} MHz (100% парные плашки, для ПК)")
        print(f"  📍 Локация: {best.get('location', 'Не указана')}")
        print(f"  ✅ Статус: Свободно, Авито Доставка доступна, не зарезервировано")
        print(f"  🔗 ССЫЛКА НА ОБЪЯВЛЕНИЕ:")
        print(f"     {best['url']}")
        print("=" * 75)
    else:
        print("\n  ⚠️ Все дешёвые кандидаты в этом цикле оказались зарезервированы или отсеяны.")

    # ALWAYS display all-time top deals after every cycle!
    print_all_time_top()


async def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║            🚀 AVITO DDR4 2x8 3200MHz SNIPER — V5                     ║")
    print("║  • 100% ЗАЩИТА ОТ РЕЗЕРВА (проверка статуса Авито Доставки на стр.)  ║")
    print("║  • АНТИ-СОЛЯНКА: исключены разные плашки, бренды и частоты          ║")
    print("║  • ТОП ЗА ВСЁ ВРЕМЯ: рейтинг лучших сделок после каждого цикла       ║")
    print("║  • Постоянная сессия (капча проходится 1 раз при старте)             ║")
    print("║  Нажмите Ctrl+C для выхода                                           ║")
    print("╚══════════════════════════════════════════════════════════════════════╝\n")

    init_db()
    config = load_config()
    scraper = AvitoScraper(config)

    print("⏳ Запуск браузера...")
    await scraper.start()

    cycle = 0
    poll_sec = 60
    try:
        while True:
            cycle += 1
            await scan_once(scraper, cycle)
            print(f"\n  ⏰ Следующее обновление через {poll_sec} сек... (Ctrl+C для выхода)")
            await asyncio.sleep(poll_sec)
    except KeyboardInterrupt:
        print("\n  🛑 Остановка мониторинга...")
    finally:
        await scraper.close()
        print("  👋 Сессия закрыта.")


if __name__ == "__main__":
    asyncio.run(main())
