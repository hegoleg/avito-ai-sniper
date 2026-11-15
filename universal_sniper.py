"""
Universal Avito AI Sniper — Умный мониторинг любых товаров на Авито.
Позволяет искать любой товар (видеокарты, процессоры, телефоны, консоли, авто, велосипеды и т.д.).
- Постоянная сессия (капча проходится 1 раз).
- 100% защита от зарезервированных товаров («Авито Доставка / в резерве»).
- УМНЫЙ ОТСЕВ:
  * Защита от мобильных видеокарт (3070m, 3060m, Mobile чипы, Франкенштейны, MXM).
  * Защита от кулеров, коробок, бэкплейтов и радиаторов.
  * Защита от дефектов, артефактов, запчастей, реплик и ловушек («цена за 1 шт»).
  * Двухпроходная маскировка отрицаний ("не битая", "артефакты отсутствуют", "в комплекте коробка").
- УМНАЯ ОЧЕРЕДЬ И ДЕДУПЛИКАЦИЯ:
  * Приоритет свежих поступлений (s=104) во главе очереди.
  * Отслеживание снижения цен на известные лоты.
  * Кеширование проверок с защитой от повторных открытий вкладок.
- АНТИБАН-ЗАЩИТА:
  * Случайный джиттер пауз между запросами (1.8-3.5с).
  * Случайный джиттер интервала циклов (±20%).
  * Экспоненциальный откат (BackoffManager) при блокировках и капче.
- ЕДИНЫЙ ПАЙПЛАЙН УВЕДОМЛЕНИЙ:
  * Прямая отправка находок в Telegram с универсальным форматированием.
  * Мгновенные фото-оповещения при обнаружении капчи / блокировки IP.
- ЧЁТКИЙ ТОП ПО ЗАПРОСУ: рейтинг сделок за всё время строго изолирован по каждому товару.
- Поддерживает быстрые пресеты, CLI-параметры и интерактивный ввод.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

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
    get_stats
)
from scraper import AvitoScraper
from notifier import TelegramNotifier
from anti_bait import check_listing_bait, check_description_bait
from negation_filter import (
    DEFAULT_EXCLUDES,
    mask_negations,
    is_reserved_text,
    check_excludes
)
from verification_queue import (
    VerificationQueue,
    InspectionStatus,
    async_sleep_jitter,
    async_request_pause,
    BackoffManager
)
from hardware_catalog import search_catalog, get_item_by_id
from ram_knowledge import (
    SERVER_PATTERNS as RAM_SERVER_PATTERNS,
    LAPTOP_PATTERNS as RAM_LAPTOP_PATTERNS,
    MISMATCH_PATTERNS as RAM_MISMATCH_PATTERNS,
    extract_ram_type,
    extract_capacity_and_kit,
    extract_frequency
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("UniversalSniper")
logging.getLogger("playwright").setLevel(logging.WARNING)

PRESETS_PATH = os.path.join(PROJECT_ROOT, "presets.json")

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

        # Auto-detect if this is a RAM search to protect against laptop / server / capacity mismatch
        self.is_ram_search = bool(re.search(r"\b(ddr\d?|озу|память|ram)\b", q_lower))
        self.allow_sodimm = bool(re.search(r"\b(sodimm|so-dimm|ноутбук|laptop|ноута)\b", q_lower))
        self.allow_server = bool(re.search(r"\b(ecc|reg|regg|сервер|server)\b", q_lower))

        # Extract target RAM capacity if specified in query (e.g. 16gb, 32gb, 8gb, 64gb)
        self.target_ram_capacity = None
        if self.is_ram_search:
            m_cap = re.search(r"\b(4|8|16|32|64|128)\s*(?:gb|гб)\b", q_lower)
            if m_cap:
                self.target_ram_capacity = int(m_cap.group(1))

        # Extract target RAM frequency if specified in query (e.g. 3200, 3600, etc.)
        self.target_ram_freq = None
        if self.is_ram_search:
            m_freq = re.search(r"\b(1600|2133|2400|2666|2933|3000|3200|3600|4000|4800|5200|5600|6000)\b", q_lower)
            if m_freq:
                self.target_ram_freq = int(m_freq.group(1))

    def quick_filter(self, item: dict) -> Tuple[bool, str]:
        """
        Fast preliminary filter applied on search card snippet.
        Uses two-pass negation masking to protect legitimate listings.
        """
        if item.get("is_reserved"):
            return False, "Зарезервировано (метка в карточке)"

        title = item.get("title", "")
        snippet = item.get("raw_description", "")
        raw_full_text = f"{title} {snippet}"

        if is_reserved_text(raw_full_text):
            return False, "Зарезервировано (в тексте)"

        # Two-pass negation evaluation: mask out legitimate negations & packaging phrases
        masked_text = mask_negations(raw_full_text)
        eval_text = re.sub(r'(\d+)\s*[хx]\b', r'\1x', masked_text.lower())

        # Check default trash / defect words on masked text
        for p in DEFAULT_EXCLUDES:
            if re.search(p, eval_text):
                return False, "Дефект, запчасти, копия или ловушка цены"

        # Check anti-bait on original snippet: multi-model catalog, fake price, barter, pawnshop
        is_bait, bait_reason = check_listing_bait(title, snippet, query=self.query)
        if is_bait:
            return False, bait_reason

        # Check GPU Mobile / Frankenstein cards
        if self.is_gpu_search and not self.allow_mobile:
            for p in GPU_MOBILE_PATTERNS:
                if re.search(p, eval_text):
                    return False, "Мобильная видеокарта / чип от ноутбука (Mobile / M-версия)"
            for p in GPU_ACCESSORY_PATTERNS:
                if re.search(p, eval_text):
                    return False, "Кулер, охлаждение или коробка (не сама видеокарта)"

        # Check RAM auto-protections (laptop, server, mismatch, capacity, frequency)
        if self.is_ram_search:
            if not self.allow_sodimm:
                for p in RAM_LAPTOP_PATTERNS:
                    if re.search(p, eval_text):
                        return False, "Память для ноутбука (SO-DIMM / ноутбук)"
            if not self.allow_server:
                for p in RAM_SERVER_PATTERNS:
                    if re.search(p, eval_text):
                        return False, "Серверная память (ECC REG)"
            for p in RAM_MISMATCH_PATTERNS:
                if re.search(p, eval_text):
                    return False, "Разнопарные плашки / солянка"

            # Check capacity mismatch
            if self.target_ram_capacity:
                cap, is_kit = extract_capacity_and_kit(raw_full_text)
                if cap is not None and cap < self.target_ram_capacity:
                    return False, f"Объём памяти ({cap} ГБ) меньше искомого ({self.target_ram_capacity} ГБ)"
                if self.target_ram_capacity >= 16:
                    if re.search(r"\b8\s*(?:gb|гб)\b", eval_text) and not re.search(r"\b(?:16|32|64)\s*(?:gb|гб)?\b|2\s*[xх*]\s*8", eval_text):
                        return False, "Объём памяти 8 ГБ (искали 16+ ГБ)"

            # Check frequency mismatch
            if self.target_ram_freq and self.target_ram_freq >= 3000:
                if re.search(r"\b(2133|2400|2666)\b", eval_text) and str(self.target_ram_freq) not in eval_text:
                    return False, f"Частота памяти ниже требуемой ({self.target_ram_freq} МГц)"

        # Check user exclude words (with word boundaries on masked text)
        for ew in self.exclude_words:
            pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(ew) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
            if re.search(pattern, eval_text):
                return False, f"Минус-слово: '{ew}'"

        # Check required words (with word boundaries on raw text)
        norm_raw = re.sub(r'(\d+)\s*[хx]\b', r'\1x', raw_full_text.lower())
        if self.required_words:
            for rw in self.required_words:
                pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(rw) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
                if not re.search(pattern, norm_raw):
                    return False, f"Отсутствует обязательное слово: '{rw}'"

        return True, "OK"

    def verify_full_details(self, combined_text: str, is_page_reserved: bool = False, is_closed: bool = False) -> Tuple[bool, str]:
        """
        Deep verification applied on item page full description and parameters.
        Scoped action block reservation check and negation masking applied.
        """
        if is_closed:
            return False, "Объявление снято с публикации / закрыто"

        if is_page_reserved:
            return False, "Товар зарезервирован (Авито Доставка)"

        if not combined_text or not combined_text.strip():
            return False, "Не удалось получить описание товара (таймаут, капча или блок)"

        if is_reserved_text(combined_text):
            return False, "Товар зарезервирован / в резерве"

        masked_text = mask_negations(combined_text)
        eval_text = re.sub(r'(\d+)\s*[хx]\b', r'\1x', masked_text.lower())

        for p in DEFAULT_EXCLUDES:
            if re.search(p, eval_text):
                return False, "В описании упомянут дефект, копия, запчасти или коробка"

        # Check anti-bait in full description / specs
        is_bait, bait_reason = check_description_bait(combined_text.lower(), query=self.query)
        if is_bait:
            return False, bait_reason

        # Check GPU Mobile in full text
        if self.is_gpu_search and not self.allow_mobile:
            for p in GPU_MOBILE_PATTERNS:
                if re.search(p, eval_text):
                    return False, "Мобильная видеокарта / ноутбучный чип в описании (Mobile / M-чип)"
            for p in GPU_ACCESSORY_PATTERNS:
                if re.search(p, eval_text):
                    return False, "В описании указано охлаждение / кулер, а не видеокарта"

        # Check RAM auto-protections in full text and specifications
        if self.is_ram_search:
            if not self.allow_sodimm:
                for p in RAM_LAPTOP_PATTERNS:
                    if re.search(p, eval_text):
                        return False, "В описании указана память для ноутбука (SO-DIMM)"
                if any(k in eval_text for k in ["sodimm", "so-dimm", "ноутбук", "для ноутбука"]):
                    return False, "Форм-фактор SODIMM / для ноутбука в описании или характеристиках"
            if not self.allow_server:
                for p in RAM_SERVER_PATTERNS:
                    if re.search(p, eval_text):
                        return False, "Серверная память (ECC REG) в описании"
            for p in RAM_MISMATCH_PATTERNS:
                if re.search(p, eval_text):
                    return False, "В описании указаны разнопарные плашки / солянка"

            if self.target_ram_capacity:
                cap, is_kit = extract_capacity_and_kit(combined_text)
                if cap is not None and cap < self.target_ram_capacity:
                    return False, f"Объём памяти в описании ({cap} ГБ) меньше искомого ({self.target_ram_capacity} ГБ)"
                if self.target_ram_capacity >= 16:
                    # Check characteristics: "Объём одного модуля, ГБ: 8" and "Количество модулей в комплекте: 1"
                    m_one = re.search(r"объём одного модуля[^\d]*(\d+)", eval_text)
                    m_cnt = re.search(r"количество модулей[^\d]*(\d+)", eval_text)
                    if m_one and m_cnt:
                        total_spec_cap = int(m_one.group(1)) * int(m_cnt.group(1))
                        if total_spec_cap < self.target_ram_capacity:
                            return False, f"Общий объём по характеристикам ({total_spec_cap} ГБ) меньше искомого ({self.target_ram_capacity} ГБ)"
                    elif re.search(r"\b8\s*(?:gb|гб)\b", eval_text) and not re.search(r"\b(?:16|32|64)\s*(?:gb|гб)?\b|2\s*[xх*]\s*8", eval_text):
                        return False, "Объём памяти 8 ГБ в описании (искали 16+ ГБ)"

            if self.target_ram_freq and self.target_ram_freq >= 3000:
                if re.search(r"\b(2133|2400|2666)\b", eval_text) and str(self.target_ram_freq) not in eval_text:
                    return False, f"Частота памяти в описании ниже требуемой ({self.target_ram_freq} МГц)"

        for ew in self.exclude_words:
            pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(ew) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
            if re.search(pattern, eval_text):
                return False, f"Минус-слово в описании: '{ew}'"

        norm_combined = re.sub(r'(\d+)\s*[хx]\b', r'\1x', combined_text.lower())
        if self.required_words:
            for rw in self.required_words:
                pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(rw) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
                if not re.search(pattern, norm_combined):
                    return False, f"В описании нет обязательного слова: '{rw}'"

        return True, "OK"


def print_all_time_top(query: str):
    """Prints top verified deals recorded for this query in the database."""
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


async def scan_target_once(
    scraper: AvitoScraper,
    target: SearchTarget,
    cycle_num: int,
    queue: Optional[VerificationQueue] = None,
    notifier: Optional[TelegramNotifier] = None,
    backoff: Optional[BackoffManager] = None
):
    """
    Executes a single cycle with dual search (s=1 and s=104), queue deduplication,
    anti-ban randomized pause jitter, scoped deep verification, and Telegram alerts.
    """
    now_str = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*75}")
    print(f"  🔍 ЦИКЛ #{cycle_num} | Время: {now_str}")
    print(f"  🎯 Цель: '{target.query}' | Локация: {target.location} | Цены: {target.min_price or 0} — {target.max_price or '∞'} ₽")
    if target.is_gpu_search and not target.allow_mobile:
        print("  🛡️ Активна защита: отсев мобильных чипов (m-версий) и кулеров")
    print(f"{'='*75}")

    # 1. Scan s=1 (Cheapest baseline)
    print(f"  📡 Опрос выдачи: Самые дешёвые ({target.query}, s=1)...")
    items_1 = await scraper.scrape_new_listings(
        max_items=35,
        query=target.query,
        sort_by="1",
        min_price=target.min_price,
        max_price=target.max_price,
        location=target.location,
        category=""
    )

    # Anti-ban randomized pause between queries
    await async_request_pause(1.5, 3.0)

    # 2. Scan s=104 (Fresh arrivals)
    print(f"  📡 Опрос выдачи: Свежие поступления ({target.query}, s=104)...")
    items_104 = await scraper.scrape_new_listings(
        max_items=35,
        query=target.query,
        sort_by="104",
        min_price=target.min_price,
        max_price=target.max_price,
        location=target.location,
        category=""
    )

    if not items_1 and not items_104:
        print("  ⏳ Нет данных с Авито (проверьте интернет или окно браузера).")
        if backoff:
            delay = backoff.record_error()
            logger.warning("Scraper returned zero items; backoff delay: %.1fs", delay)
        print_all_time_top(target.query)
        return
    elif backoff:
        backoff.record_success()

    # 3. Filter items and record in database
    passed_1 = []
    passed_104 = []
    rejection_reasons: Dict[str, int] = {}

    for it in items_1:
        iid = it.get("item_id")
        p = it.get("price")
        try:
            save_listing(it)
        except Exception:
            pass

        ok, reason = target.quick_filter(it)
        if ok and p and p > 0:
            passed_1.append(it)
        else:
            if iid and queue:
                status = InspectionStatus.REJECTED_RESERVED if "Зарезервировано" in reason else InspectionStatus.REJECTED_STATIC
                queue.record_result(iid, status, p or 0, reason)
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    for it in items_104:
        iid = it.get("item_id")
        p = it.get("price")
        try:
            save_listing(it)
        except Exception:
            pass

        ok, reason = target.quick_filter(it)
        if ok and p and p > 0:
            passed_104.append(it)
        else:
            if iid and queue:
                status = InspectionStatus.REJECTED_RESERVED if "Зарезервировано" in reason else InspectionStatus.REJECTED_STATIC
                queue.record_result(iid, status, p or 0, reason)
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    # 4. Smart candidate prioritization & deduplication
    if queue:
        candidates = queue.prioritize_candidates(items_104=passed_104, items_1=passed_1, max_count=7)
    else:
        comb = {it["item_id"]: it for it in (passed_104 + passed_1) if it.get("item_id")}.values()
        candidates = sorted(comb, key=lambda x: x["price"])[:7]

    total_collected = len(set(it.get("item_id") for it in (items_1 + items_104) if it.get("item_id")))
    total_passed = len(set(it.get("item_id") for it in (passed_1 + passed_104) if it.get("item_id")))
    print(f"  📊 Всего в выборке: {total_collected} | Прошло базовый фильтр: {total_passed} | Отобрано в очередь: {len(candidates)}")

    if not candidates:
        if rejection_reasons:
            print("  ⚠️ Причины отсева лотов базовым фильтром:")
            for r_msg, r_count in sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True)[:4]:
                print(f"     • {r_msg}: {r_count} шт.")
        print("  ℹ️ В текущем цикле новых подходящих лотов для проверки нет (все проверены или отсеяны).")
        print_all_time_top(target.query)
        return

    # 5. Deep verification of prioritized candidates
    verified_deals = []
    print("\n  🔍 Глубокая проверка кандидатов (проверяем описание, бронь, мобильные чипы)...")

    for it in candidates:
        url = it.get("url")
        title = it.get("title")
        price = it.get("price")
        item_id = it.get("item_id")
        queue_prio = it.get("_queue_priority", 3)

        # Anti-ban pause before loading full product page
        await async_request_pause(1.8, 3.5)

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
            print(f"   ⚠️ [ОТСЕВ] {price:,} ₽ | {title} -> {reject_reason}".replace(",", " "))
            if item_id:
                if queue:
                    status = (
                        InspectionStatus.REJECTED_RESERVED
                        if (is_page_reserved or "резерв" in reject_reason.lower())
                        else InspectionStatus.REJECTED_STATIC
                    )
                    queue.record_result(item_id, status, price, reject_reason)
                mark_deal_reserved_or_inactive(item_id)
            continue

        deal_entry = {
            "item_id": str(item_id),
            "title": title,
            "price": price,
            "url": url,
            "location": it.get("location", ""),
            "specs": target.query,
            "delivery_info": details.get("delivery_info", ""),
            "deal_rating": "TOP_DEAL" if queue_prio == 1 else "GOOD_DEAL"
        }
        verified_deals.append(deal_entry)

        if queue and item_id:
            queue.record_result(item_id, InspectionStatus.VERIFIED_DEAL, price, "OK")

        try:
            save_verified_deal(deal_entry, query=target.query)
        except Exception as e:
            logger.debug("Save verified failed: %s", e)

        print(f"   ✅ [ПОДТВЕРЖДЕНО: СВОБОДНО] {price:,} ₽ | {title}".replace(",", " "))

        # Dispatch Telegram notification
        if notifier:
            try:
                alert_res = notifier.send_deal_alert(deal_entry, target_name=target.name)
                if asyncio.iscoroutine(alert_res):
                    await alert_res
            except Exception as notif_err:
                logger.error("Failed to send deal alert to Telegram: %s", notif_err)

    if verified_deals:
        best = verified_deals[0]
        best_price = best["price"]

        print("\n" + "🔥" * 38)
        print("  🎯 ЛУЧШЕЕ ПРЕДЛОЖЕНИЕ ЭТОГО ЦИКЛА (АКТИВНОЕ, БЕЗ БРОНИ):")
        print("🔥" * 38)
        print(f"  📦 {best['title']}")
        print(f"  💰 ЦЕНА: {best_price:,} ₽".replace(",", " "))
        print(f"  📍 Локация: {best.get('location', 'Не указана')}")
        print("  ✅ Статус: Подтверждено, активно, Авито Доставка проверена")
        print("  🔗 ССЫЛКА НА ОБЪЯВЛЕНИЕ:")
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
    parser.add_argument("--chip", type=str, default=None, help="Выбрать готовый чип из каталога комплектующих (например, '3070', '4060', '7500f')")
    parser.add_argument("--interval", type=int, default=60, help="Интервал обновления в секундах")
    parser.add_argument("--setup", action="store_true", help="Открыть окно браузера для прохождения капчи")
    parser.add_argument("--test-notify", action="store_true", help="Отправить тестовое уведомление в Telegram")
    parser.add_argument("--stats", action="store_true", help="Показать статистику базы данных")
    parser.add_argument("--scan", action="store_true", help="Выполнить один цикл сканирования и завершить работу")
    parser.add_argument("--loop", action="store_true", help="Запустить постоянный цикл мониторинга")

    args = parser.parse_args()

    # CLI utility options
    if args.setup:
        print("Запуск сессии в видимом окне Chrome для настройки / прохождения капчи...")
        from setup_session import setup_session
        await setup_session()
        return

    if args.test_notify:
        config = load_config()
        notifier = TelegramNotifier(bot_token=config.telegram_bot_token, chat_id=config.telegram_chat_id)
        print("Отправка тестового уведомления в Telegram...")
        ok = await notifier.test_connection()
        if ok:
            print("Тестовое уведомление успешно отправлено!")
        else:
            print("Не удалось отправить тестовое уведомление. Проверьте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.")
        return

    if args.stats:
        init_db()
        stats = get_stats()
        print("\nСтатистика базы данных Avito AI Sniper:")
        print(f"  • Всего проанализировано объявлений: {stats['total_seen']}")
        print(f"  • Найдено выгодных сделок:           {stats['total_deals']}")
        print(f"  • Отправлено уведомлений:            {stats['total_notified']}\n")
        return

    presets = load_presets()

    if args.chip:
        catalog_matches = search_catalog(args.chip, limit=1)
        if not catalog_matches:
            print(f"⚠️ Чип '{args.chip}' не найден в каталоге. Запустите без аргументов для интерактивного меню.")
            return
        chip_item = catalog_matches[0]
        print(f"✅ Выбран чип из каталога: {chip_item['name']} ({chip_item.get('specs', '')})")
        target = SearchTarget(
            name=chip_item["name"],
            query=chip_item["query"],
            min_price=args.min if args.min is not None else chip_item.get("min_price"),
            max_price=args.max if args.max is not None else chip_item.get("max_price"),
            location=args.loc,
            required_words=chip_item.get("required_words", []),
            exclude_words=chip_item.get("exclude_words", [])
        )
    elif args.preset and str(args.preset) in presets:
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
    notifier = TelegramNotifier(bot_token=config.telegram_bot_token, chat_id=config.telegram_chat_id)
    scraper = AvitoScraper(config, notifier=notifier)

    cache_dir = os.path.join(PROJECT_ROOT, "user_data")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "verification_cache.json")
    queue = VerificationQueue(cache_file=cache_file)
    backoff = BackoffManager()

    print("\n⏳ Запуск браузера...")
    await scraper.start()

    cycle = 0
    poll_sec = max(30, args.interval)
    try:
        if args.scan:
            cycle = 1
            await scan_target_once(scraper, target, cycle, queue=queue, notifier=notifier, backoff=backoff)
        else:
            while True:
                cycle += 1
                await scan_target_once(scraper, target, cycle, queue=queue, notifier=notifier, backoff=backoff)
                sleep_dur = await async_sleep_jitter(poll_sec, jitter_pct=0.20)
                print(f"\n  ⏰ Следующая проверка через {sleep_dur:.1f} сек... (Ctrl+C для выхода)")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n  🛑 Остановка снайпера...")
    finally:
        try:
            queue.save_to_json(cache_file)
            logger.info("Состояние очереди сохранено на диск.")
        except Exception as q_err:
            logger.debug("Не удалось сохранить кеш очереди: %s", q_err)

        await scraper.close()
        print("  👋 Браузерная сессия закрыта.")


if __name__ == "__main__":
    asyncio.run(main())
