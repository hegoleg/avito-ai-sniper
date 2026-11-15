"""
Universal Avito AI Sniper — Умный мониторинг любых товаров на Авито.
Позволяет искать любой товар (видеокарты, процессоры, телефоны, консоли, авто, велосипеды и т.д.).
- Постоянная сессия (капча проходится 1 раз).
- 100% защита от зарезервированных товаров («Авито Доставка / в резерве»).
- УМНЫЙ ОТСЕВ:
  * Защита от мобильных видеокарт (3070m, 3060m, Mobile чипы, Франкенштейны, MXM).
  * Защита от кулеров, коробок, бэкплейтов и радиаторов.
  * Защита от дефектов, артефактов, запчастей, реплик и ловушек («цена за 1 шт»).
- ЧЁТКИЙ ТОП ПО ЗАПРОСУ: рейтинг сделок за всё время строго изолирован по каждому товару (видеокарты не смешиваются с памятью).
- Поддерживает быстрые пресеты и интерактивный ввод.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional

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
    get_all_time_top_deals
)
from scraper import AvitoScraper
from anti_bait import check_listing_bait, check_description_bait

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("UniversalSniper")
logging.getLogger("playwright").setLevel(logging.WARNING)

PRESETS_PATH = os.path.join(PROJECT_ROOT, "presets.json")

DEFAULT_EXCLUDES = [
    r"\bна\s+запчаст(?:и|ей)\b",
    r"\bне\s+(?:включается|стартует|работает|определяется|запускает|запускается)\b",
    r"\bне\s*рабоч(?:ая|ий|ее|ие)\b",
    r"\bнеисправн(?:ая|ый|ое|ые)\b",
    r"\bс\s+дефект(?:ом|ами)\b",
    r"\bпод\s+восстановление\b",
    r"\bбитая?\b",
    r"\bотвал\b",
    r"\bартефакт(?:ы|ит)?\b",
    r"\bкод\s+43\b",
    r"\bкопи(?:я|и)\b",
    r"\bреплик(?:а|и)\b",
    r"\b(?:только\s+)?коробк(?:а|у|и)\b",
    r"\bпустая\s+коробка\b",
    r"\bаренд(?:а|у)\b",
    r"\bцена\s+(?:указана\s+)?за\s+(?:одну|1|каждую|одну\s+из)\s*(?:плашку|планку|шт|штуку)?\b",
    r"\bцена\s+за\s+(?:штуку|плашку|планку|1\s*шт)\b",
]

GPU_MOBILE_PATTERNS = [
    r"\b(?:\d{4}|rtx\s*\d{4}|rx\s*\d{4})\s*m\b",
    r"\bmobile\b",
    r"\blaptop\b",
    r"\bмобайл\b",
    r"\bмоб(?:\.|\s+чип|\s+верси)\b",
    r"\bноутбучн(?:ая|ый|ое|ые|ую)\b",
    r"\bдля\s+ноутбук(?:а|ов)\b",
    r"\bна\s+(?:мобильном|ноутбучном)\s+чипе\b",
    r"\bчип\s+от\s+ноутбука\b",
    r"\bноутбучный\s+чип\b",
    r"\bфранкенштейн\b",
    r"\bmxm\b",
    r"\bм-верси(?:я|и)\b",
    r"\bm-верси(?:я|и)\b",
    r"\bверси(?:я|и)\s+m\b",
    r"\bgn20-[a-z0-9]+\b"
]

GPU_ACCESSORY_PATTERNS = [
    r"\b(?:кулер|кулеры|вентилятор|вентиляторы|радиатор|охлаждение|бэкплейт|кожух|термопрокладки)\s+(?:для|от|к)\b",
    r"\b(?:только\s+)?(?:охлаждение|радиатор|кулер|коробка|бэкплейт)\b",
    r"\bбез\s+(?:чипа|платы|видеочипа)\b"
]


def load_presets() -> dict:
    if os.path.exists(PRESETS_PATH):
        try:
            with open(PRESETS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


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


class SearchTarget:
    def __init__(
        self,
        name: str,
        query: str,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        location: str = "all",
        required_words: Optional[List[str]] = None,
        exclude_words: Optional[List[str]] = None
    ):
        self.name = name
        self.query = query.strip()
        self.min_price = min_price
        self.max_price = max_price
        self.location = location.strip() or "all"
        self.required_words = [re.sub(r'(\d+)\s*[хx]\b', r'\1x', w.lower()) for w in (required_words or [])]
        self.exclude_words = [re.sub(r'(\d+)\s*[хx]\b', r'\1x', w.lower()) for w in (exclude_words or [])]

        # Auto-detect if this is a GPU search to protect against mobile / accessories
        q_lower = self.query.lower()
        self.is_gpu_search = bool(re.search(r"\b(rtx|gtx|rx|видеокарт|geforce|radeon|gpu)\b", q_lower))
        self.allow_mobile = bool(re.search(r"\b(mobile|мобайл|\bm\b|ноутбук)\b", q_lower))

    def quick_filter(self, item: dict) -> tuple[bool, str]:
        if item.get("is_reserved"):
            return False, "Зарезервировано (метка в карточке)"

        title = item.get("title", "")
        snippet = item.get("raw_description", "")
        full_text = f"{title} {snippet}".lower()
        full_text = re.sub(r'(\d+)\s*[хx]\b', r'\1x', full_text)

        if is_reserved_text(full_text):
            return False, "Зарезервировано (в тексте)"

        # Check default trash / defect words
        for p in DEFAULT_EXCLUDES:
            if re.search(p, full_text):
                return False, "Дефект, запчасти, копия или ловушка цены"

        # Check anti-bait: multi-model catalog, fake price, barter, pawnshop, SEO comparison
        is_bait, bait_reason = check_listing_bait(title, snippet, query=self.query)
        if is_bait:
            return False, bait_reason

        # Check GPU Mobile / Frankenstein cards
        if self.is_gpu_search and not self.allow_mobile:
            for p in GPU_MOBILE_PATTERNS:
                if re.search(p, full_text):
                    return False, "Мобильная видеокарта / чип от ноутбука (Mobile / M-версия)"
            for p in GPU_ACCESSORY_PATTERNS:
                if re.search(p, full_text):
                    return False, "Кулер, охлаждение или коробка (не сама видеокарта)"

        # Check user exclude words (with word boundaries)
        for ew in self.exclude_words:
            pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(ew) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
            if re.search(pattern, full_text):
                return False, f"Минус-слово: '{ew}'"

        # Check required words (with word boundaries)
        if self.required_words:
            for rw in self.required_words:
                pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(rw) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
                if not re.search(pattern, full_text):
                    return False, f"Отсутствует обязательное слово: '{rw}'"

        return True, "OK"

    def verify_full_details(self, combined_text: str, is_page_reserved: bool = False) -> tuple[bool, str]:
        if is_page_reserved:
            return False, "Товар зарезервирован (Авито Доставка)"

        if not combined_text:
            return True, "OK"

        t = combined_text.lower()
        t = re.sub(r'(\d+)\s*[хx]\b', r'\1x', t)
        if is_reserved_text(t):
            return False, "Товар зарезервирован / в резерве"

        for p in DEFAULT_EXCLUDES:
            if re.search(p, t):
                return False, "В описании упомянут дефект, копия, запчасти или коробка"

        # Check anti-bait in full description / specs
        is_bait, bait_reason = check_description_bait(t, query=self.query)
        if is_bait:
            return False, bait_reason

        # Check GPU Mobile in full text
        if self.is_gpu_search and not self.allow_mobile:
            for p in GPU_MOBILE_PATTERNS:
                if re.search(p, t):
                    return False, "Мобильная видеокарта / ноутбучный чип в описании (Mobile / M-чип)"
            for p in GPU_ACCESSORY_PATTERNS:
                if re.search(p, t):
                    return False, "В описании указано охлаждение / кулер, а не видеокарта"

        for ew in self.exclude_words:
            pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(ew) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
            if re.search(pattern, t):
                return False, f"Минус-слово в описании: '{ew}'"

        if self.required_words:
            for rw in self.required_words:
                pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(rw) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
                if not re.search(pattern, t):
                    return False, f"В описании нет обязательного слова: '{rw}'"

        return True, "OK"


def print_all_time_top(query: str):
    top_deals = get_all_time_top_deals(query=query, limit=5)
    print("\n" + "🌟" * 38)
    print(f"  🏆 ТОП ЛУЧШИХ СДЕЛОК ЗА ВСЁ ВРЕМЯ ПО ЗАПРОСУ '{query}':")
    print("🌟" * 38)

    if not top_deals:
        print(f"  ℹ️ По запросу '{query}' в базе пока нет подтверждённых сделок (наполняется в процессе)...")
        print("=" * 75)
        return

    for idx, deal in enumerate(top_deals, start=1):
        p = deal["price"]
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"[{idx}]"
        print(f"  {medal} {p:,} ₽ — {deal.get('title')} ({deal.get('location', 'РФ')})".replace(",", " "))
        print(f"      🔗 {deal.get('url')}")
    print("=" * 75)


async def scan_target_once(scraper: AvitoScraper, target: SearchTarget, cycle_num: int):
    now_str = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*75}")
    print(f"  🔍 ЦИКЛ #{cycle_num} | Время: {now_str}")
    print(f"  🎯 Цель: '{target.query}' | Локация: {target.location} | Цены: {target.min_price or 0} — {target.max_price or '∞'} ₽")
    if target.is_gpu_search and not target.allow_mobile:
        print(f"  🛡️ Активна защита: отсев мобильных чипов (m-версий) и кулеров")
    print(f"{'='*75}")

    scans = [
        {"sort": "1",   "label": f"Самые дешёвые ({target.query}, s=1)"},
        {"sort": "104", "label": f"Свежие поступления ({target.query}, s=104)"},
    ]

    collected = {}
    for sc in scans:
        print(f"  📡 Опрос выдачи: {sc['label']}...")
        items = await scraper.scrape_new_listings(
            max_items=35,
            query=target.query,
            sort_by=sc["sort"],
            min_price=target.min_price,
            max_price=target.max_price,
            location=target.location,
            category=""
        )
        for it in items:
            iid = it.get("item_id")
            if iid and iid not in collected:
                collected[iid] = it
        await asyncio.sleep(1.0)

    if not collected:
        print("  ⏳ Нет данных с Авито (проверьте интернет или окно браузера).")
        print_all_time_top(target.query)
        return

    # Fast pre-filtering
    candidates = []
    rejection_reasons = {}
    for it in collected.values():
        ok, reason = target.quick_filter(it)
        if ok:
            p = it.get("price")
            if p and p > 0:
                candidates.append(it)
        else:
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        try:
            save_listing(it)
        except Exception:
            pass

    print(f"  📊 Всего в выборке: {len(collected)} | Прошло базовый фильтр: {len(candidates)}")

    if not candidates:
        if rejection_reasons:
            print("  ⚠️ Причины отсева лотов базовым фильтром:")
            for r_msg, r_count in sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True)[:4]:
                print(f"     • {r_msg}: {r_count} шт.")
        print("  ℹ️ В текущем цикле новых подходящих лотов нет.")
        print_all_time_top(target.query)
        return

    # Sort candidates by price ascending
    candidates.sort(key=lambda x: x["price"])

    verified_deals = []
    print("\n  🔍 Глубокая проверка кандидатов (проверяем описание, бронь, мобильные чипы)...")

    for it in candidates[:7]:
        url = it.get("url")
        title = it.get("title")
        price = it.get("price")
        item_id = it.get("item_id")

        details = await scraper.get_item_full_details(url)
        combined_text = details.get("combined_text", "")
        is_page_reserved = details.get("is_page_reserved", False)

        valid, reject_reason = target.verify_full_details(combined_text, is_page_reserved=is_page_reserved)
        if not valid:
            print(f"   ⚠️ [ОТСЕВ] {price:,} ₽ | {title} -> {reject_reason}".replace(",", " "))
            if item_id:
                mark_deal_reserved_or_inactive(item_id)
            continue

        deal_entry = {
            "item_id": str(item_id),
            "title": title,
            "price": price,
            "url": url,
            "location": it.get("location", ""),
            "specs": target.query
        }
        verified_deals.append(deal_entry)

        try:
            save_verified_deal(deal_entry, query=target.query)
        except Exception as e:
            logger.debug("Save verified failed: %s", e)

        print(f"   ✅ [ПОДТВЕРЖДЕНО: СВОБОДНО, ДЕСКТОП] {price:,} ₽ | {title}".replace(",", " "))

    if verified_deals:
        best = verified_deals[0]
        best_price = best["price"]

        print("\n" + "🔥" * 38)
        print("  🎯 ЛУЧШЕЕ ПРЕДЛОЖЕНИЕ ЭТОГО ЦИКЛА (АКТИВНОЕ, БЕЗ БРОНИ):")
        print("🔥" * 38)
        print(f"  📦 {best['title']}")
        print(f"  💰 ЦЕНА: {best_price:,} ₽".replace(",", " "))
        print(f"  📍 Локация: {best.get('location', 'Не указана')}")
        print(f"  ✅ Статус: Десктопная версия, свободно, Авито Доставка доступна")
        print(f"  🔗 ССЫЛКА НА ОБЪЯВЛЕНИЕ:")
        print(f"     {best['url']}")
        print("=" * 75)
    else:
        print("\n  ⚠️ Все дешёвые кандидаты в этом цикле оказались зарезервированы, мобильными чипами или отсеяны.")

    print_all_time_top(target.query)


def interactive_wizard() -> SearchTarget:
    presets = load_presets()

    print("\n" + "╔" + "═" * 70 + "╗")
    print("║        🎯 УНИВЕРСАЛЬНЫЙ АВИТО СНАЙПЕР — ВЫБОР ЦЕЛИ МОНИТОРИНГА        ║")
    print("╚" + "═" * 70 + "╝\n")

    if presets:
        print("Готовые быстрые шаблоны:")
        for k, p in presets.items():
            price_info = f"({p.get('min_price', 0)} – {p.get('max_price', '∞')} ₽)"
            print(f"  [{k}] {p['name']} {price_info}")
        print("  [0] 🔍 СВОЙ ПОИСК (ввести любой товар вручную)\n")

        choice = input("Выберите номер шаблона или 0 для своего поиска [0]: ").strip()
        if choice in presets:
            sel = presets[choice]
            print(f"\n✅ Выбран шаблон: {sel['name']}")
            return SearchTarget(
                name=sel.get("name", sel["query"]),
                query=sel["query"],
                min_price=sel.get("min_price"),
                max_price=sel.get("max_price"),
                location=sel.get("location", "all"),
                required_words=sel.get("required_words"),
                exclude_words=sel.get("exclude_words")
            )

    print("\n--- НАСТРОЙКА СВОЕГО ПОИСКА ---")
    query = input("1. Что ищем? (например: RTX 3070, Ryzen 5600, iPhone 13, Велосипед): ").strip()
    while not query:
        query = input("Запрос не может быть пустым. Что ищем?: ").strip()

    min_p_str = input("2. Минимальная цена в ₽ (нажмите Enter, чтобы не ставить): ").strip()
    min_price = int(re.sub(r"\D", "", min_p_str)) if min_p_str and re.sub(r"\D", "", min_p_str) else None

    max_p_str = input("3. Максимальная цена в ₽ (нажмите Enter, если без ограничений): ").strip()
    max_price = int(re.sub(r"\D", "", max_p_str)) if max_p_str and re.sub(r"\D", "", max_p_str) else None

    loc = input("4. Город / регион (Enter для всей России, или moskva, spb, ufa...): ").strip() or "all"

    req_str = input("5. Обязательные слова через запятую (например, для RTX 3070 введите '3070', или Enter): ").strip()
    required = [w.strip() for w in req_str.split(",") if w.strip()] if req_str else []

    excl_str = input("6. Дополнительные минус-слова через запятую (Enter для стандартных): ").strip()
    user_excludes = [w.strip() for w in excl_str.split(",") if w.strip()] if excl_str else []

    print("\n✅ Цель поиска успешно создана!")
    return SearchTarget(
        name=query,
        query=query,
        min_price=min_price,
        max_price=max_price,
        location=loc,
        required_words=required,
        exclude_words=user_excludes
    )


async def main():
    parser = argparse.ArgumentParser(description="Универсальный снайпер объявлений Авито")
    parser.add_argument("-q", "--query", type=str, help="Поисковый запрос (например: 'RTX 3070')")
    parser.add_argument("--min", type=int, default=None, help="Минимальная цена")
    parser.add_argument("--max", type=int, default=None, help="Максимальная цена")
    parser.add_argument("--loc", type=str, default="all", help="Локация (all, moskva, spb...)")
    parser.add_argument("--exclude", type=str, default="", help="Минус-слова через запятую")
    parser.add_argument("--required", type=str, default="", help="Обязательные слова через запятую")
    parser.add_argument("--preset", type=str, default=None, help="Номер готового шаблона из presets.json")
    parser.add_argument("--interval", type=int, default=60, help="Интервал обновления в секундах")

    args = parser.parse_args()

    presets = load_presets()

    if args.preset and str(args.preset) in presets:
        sel = presets[str(args.preset)]
        target = SearchTarget(
            name=sel.get("name", sel["query"]),
            query=sel["query"],
            min_price=sel.get("min_price"),
            max_price=sel.get("max_price"),
            location=sel.get("location", "all"),
            required_words=sel.get("required_words"),
            exclude_words=sel.get("exclude_words")
        )
    elif args.query:
        req = [w.strip() for w in args.required.split(",") if w.strip()]
        exc = [w.strip() for w in args.exclude.split(",") if w.strip()]
        target = SearchTarget(
            name=args.query,
            query=args.query,
            min_price=args.min,
            max_price=args.max,
            location=args.loc,
            required_words=req,
            exclude_words=exc
        )
    else:
        target = interactive_wizard()

    init_db()
    config = load_config()
    scraper = AvitoScraper(config)

    print("\n⏳ Запуск браузера...")
    await scraper.start()

    cycle = 0
    poll_sec = max(30, args.interval)
    try:
        while True:
            cycle += 1
            await scan_target_once(scraper, target, cycle)
            print(f"\n  ⏰ Следующая проверка через {poll_sec} сек... (Ctrl+C для выхода)")
            await asyncio.sleep(poll_sec)
    except KeyboardInterrupt:
        print("\n  🛑 Остановка снайпера...")
    finally:
        await scraper.close()
        print("  👋 Браузерная сессия закрыта.")


if __name__ == "__main__":
    asyncio.run(main())
