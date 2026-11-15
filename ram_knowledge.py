"""
RAM Knowledge Base and Heuristic Analysis Rules
Provides market benchmarks, regex parsers, and gotchas detection for PC Memory (RAM).
"""

import re
from typing import Dict, Any, List, Optional, Tuple

# Market benchmarks (typical used prices in RUB on Avito)
# UPDATED Oct 2026 — Memory crisis! Prices ~2-3x higher than 2024 levels.
# key: (ram_type, capacity_gb, is_kit) -> (market_fair, good_deal_threshold, top_deal_threshold)
BENCHMARKS = {
    # DDR4 (кризис памяти — цены взлетели!)
    ("DDR4", 4, False): (1200, 900, 650),
    ("DDR4", 8, False): (3500, 2700, 2000),
    ("DDR4", 16, False): (7000, 5500, 4000),   # 1x16GB
    ("DDR4", 16, True): (8000, 6000, 4500),    # 2x8GB kit
    ("DDR4", 32, False): (14000, 11000, 8500),  # 1x32GB
    ("DDR4", 32, True): (16000, 12500, 9500),   # 2x16GB kit
    ("DDR4", 64, True): (30000, 24000, 18000),  # 2x32GB kit
    
    # DDR5 (кризис памяти — цены взлетели!)
    ("DDR5", 16, False): (10000, 7500, 5500),
    ("DDR5", 16, True): (12000, 9000, 6500),
    ("DDR5", 32, False): (20000, 16000, 12000),
    ("DDR5", 32, True): (24000, 18000, 14000),  # 2x16GB kit
    ("DDR5", 64, True): (45000, 35000, 28000),  # 2x32GB kit
    
    # DDR3 (тоже подорожала из-за дефицита)
    ("DDR3", 4, False): (800, 600, 400),
    ("DDR3", 8, False): (1800, 1300, 900),
    ("DDR3", 16, True): (4000, 3000, 2200),
    ("DDR3", 16, False): (3500, 2700, 2000),
}


SERVER_PATTERNS = [
    r"\becc\b",
    r"\becc\s*[-/]?\s*reg\b",
    r"\breg\b",
    r"\bregg\b",
    r"\bregistered\b",
    r"\bрегистров(?:ая|ую|ой|ые)\b",
    r"\bбуферизованн(?:ая|ую|ой|ые)\b",
    r"\bсерверн(?:ая|ые|ую|ой|ое)\b",
    r"\bдля\s+сервер(?:а|ов)\b",
    r"\bснята\s+с\s+сервера\b",
    r"\bxeon\b",
    r"\bзионы?\b",
    r"\bзеон(?:ы|а|ов)?\b",
    r"\bксеон(?:ы|а|ов)?\b",
    r"\bx99\b",
    r"\bx79\b",
    r"\bc612\b",
    r"\bc602\b",
    r"\blga\s*2011(?:-?v?3)?\b",
    r"\b2011-?v?3\b",
    r"\bfb-dimm\b",
    r"\brdimm\b",
    r"\blrdimm\b",
    r"\br-dimm\b",
    r"\batermiter\b",
    r"\bатермитер\b",
    r"\bатермайтер\b",
    r"\bkllisre\b",
    r"\bклисре\b",
    r"\bmachinist\b",
    r"\bмашинист\b",
    r"\bhuanan(?:zhi)?\b",
    r"\bхуанан(?:джи)?\b",
    r"\bjginyue\b",
    r"\bplexhd\b",
    r"\bтолько\s+для\s+(?:x99|xeon|сервер|серверов|китайских)\b",
    r"\bне\s+(?:работает|подходит|стартует)\s+(?:на|для)\s+(?:обычных|десктоп|пк|core|ryzen|интел|amd)\b"
]

LAPTOP_PATTERNS = [
    r"\bso-dimm\b",
    r"\bsodimm\b",
    r"\bдля\s+ноутбук(?:а|ов)\b",
    r"\bноутбучн(?:ая|ые|ую)\b",
    r"\bноута\b"
]

DEFECT_PATTERNS = [
    r"\bне\s*рабоч(?:ая|ий|ее|ие)\b",
    r"\bне\s+(?:включается|стартует|работает|определяется|запускает|запускается|грузит|грузится)\b",
    r"\bнеисправн(?:ая|ый|ое|ые)\b",
    r"\bполурабоч(?:ая|ий|ее|ие)\b",
    r"\bна\s+запчаст(?:и|ей)\b",
    r"\bс\s+дефект(?:ом|ами)\b",
    r"\bбитая\b",
    r"\bсиний\s+экран\b",
    r"\bbsod\b",
    r"\bошибк(?:и|ах)\b",
    r"\bглюч(?:ит|ат|ная)\b",
    r"\bпод\s+восстановление\b",
    r"\bсгорел(?:а|и)?\b",
    r"\bотвал\b"
]

MISMATCH_PATTERNS = [
    r"\bот\s+разных\s+производител(?:ей|я)\b",
    r"\bразных\s+производител(?:ей|я)\b",
    r"\bразные\s+производител(?:и|ь)\b",
    r"\bразных\s+(?:фирм|брендов|марок|моделей)\b",
    r"\bразные\s+(?:фирмы|бренды|марки|модели)\b",
    r"\bразн(?:ые|ых|ой)\s+частот(?:а|ы|ой|ам)\b",
    r"\bразн(?:ые|ых)\s+(?:план(?:ки|ок|ками)|плаш(?:ки|ек|ками)|модул(?:и|ей|ями))\b",
    r"\b(?:планки|плашки|модули)\s+разн(?:ые|ых)\b",
    r"\bне\s*парн(?:ые|ых)\b",
    r"\bразнопарн(?:ые|ых)\b",
    r"\bразнобо(?:й|ем)\b",
    r"\bсолянк(?:а|у|ой)\b",
    r"\bсборн(?:ая|ую)\s+солянк",
    r"\bиз\s+разных\s+(?:комплектов|наборов|пар)\b",
    r"\bодн(?:а|у)\s+(?:планка|плашка)?.*?\b(?:втор|друг)(?:ая|ую)\s+(?:планка|плашка)?\b",
    r"\bперв(?:ая|ую)\s+(?:планка|плашка)?.*?\bвтор(?:ая|ую)\s+(?:планка|плашка)?\b",
]

PRICE_TRAP_PATTERNS = [
    r"\bцена\s+(?:указана\s+)?за\s+(?:одну|1|каждую|одну\s+из)\s*(?:плашку|планку|шт|штуку)?\b",
    r"\bцена\s+за\s+(?:штуку|плашку|планку)\b",
    r"\bза\s+1\s*(?:шт|штуку|плашку|планку)\b",
    r"\bцена\s+указана\s+за\s+(?:1|одну|штуку|плашку)\b",
    r"\bцена\s+за\s+каждую\b"
]


def extract_ram_type(text: str) -> Optional[str]:
    t = text.upper()
    if re.search(r"\bDDR\s*5\b", t) or "DDR5" in t:
        return "DDR5"
    if re.search(r"\bDDR\s*4\b", t) or "DDR4" in t:
        return "DDR4"
    if re.search(r"\bDDR\s*3\b", t) or "DDR3" in t:
        return "DDR3"
    if re.search(r"\bDDR\s*2\b", t) or "DDR2" in t:
        return "DDR2"
    return None


def extract_capacity_and_kit(text: str) -> Tuple[Optional[int], bool]:
    """Returns (total_capacity_gb, is_kit)."""
    t = text.lower()
    
    # Patterns like 2x8, 2х8 (cyrillic), 2*8, 2 x 8, 2 по 8, 2 планки по 8
    m_kit = re.search(r"(\d+)\s*(?:x|х|\*|×|по|(?:планки|плашки|шт)\s*по)\s*(\d+)\s*(?:гб|gb)?", t)
    if m_kit:
        count = int(m_kit.group(1))
        stick_cap = int(m_kit.group(2))
        if count in (2, 4) and stick_cap in (4, 8, 16, 32, 64):
            return count * stick_cap, True
            
    # Pattern like 32gb kit, комплект 32
    m_kit_word = re.search(r"(?:комплект|kit|пара|парой)\s*(?:из\s*2\s*шт)?\s*(\d+)\s*(?:гб|gb)", t)
    if m_kit_word:
        cap = int(m_kit_word.group(1))
        if cap in (8, 16, 32, 64, 128):
            return cap, True

    # Standalone capacity: 16gb, 32 гб
    m_single = re.search(r"\b(\d+)\s*(?:гб|gb)\b", t)
    if m_single:
        cap = int(m_single.group(1))
        if cap in (4, 8, 16, 32, 64, 128):
            # Check if text mentions kit elsewhere
            is_kit = bool(re.search(r"\b(?:комплект|kit|парой|2\s*шт|2\s*планки|2\s*плашки)\b", t))
            return cap, is_kit
            
    return None, False


def extract_frequency(text: str) -> Optional[int]:
    """Extracts frequency in MHz."""
    m = re.search(r"\b(1600|2133|2400|2666|2933|3000|3200|3600|4000|4400|4800|5200|5600|6000|6400|6800|7200|7600|8000)\s*(?:mhz|мгц)?\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def detect_form_factor(text: str) -> str:
    t = text.lower()
    for p in SERVER_PATTERNS:
        if re.search(p, t):
            return "SERVER_ECC"
    for p in LAPTOP_PATTERNS:
        if re.search(p, t):
            return "LAPTOP_SODIMM"
    return "DESKTOP_DIMM"


def detect_red_flags(text: str) -> List[str]:
    flags = []
    t = text.lower()
    
    for p in SERVER_PATTERNS:
        if re.search(p, t):
            flags.append("Серверная память (ECC REG) — не запустится на обычном домашнем ПК (Core/Ryzen)!")
            break
            
    for p in LAPTOP_PATTERNS:
        if re.search(p, t):
            flags.append("Память для ноутбука (SO-DIMM) — не влезет в обычную материнскую плату ПК")
            break
            
    for p in DEFECT_PATTERNS:
        if re.search(p, t):
            flags.append("Возможный дефект / продажа на запчасти / ошибки в работе")
            break
            
    for p in PRICE_TRAP_PATTERNS:
        if re.search(p, t):
            flags.append("Ловушка с ценой: цена указана за 1 штуку, а не за весь комплект!")
            break

    for p in MISMATCH_PATTERNS:
        if re.search(p, t):
            flags.append("Разнопарные плашки / солянка (разные производители или разные частоты)!")
            break
            
    return flags


def evaluate_deal_heuristic(title: str, price: Optional[int], description: str = "") -> Dict[str, Any]:
    """
    Fast rule-based evaluation of a RAM listing.
    Used when Gemini API is unavailable or as a pre-filter.
    """
    full_text = f"{title} {description}"
    ram_type = extract_ram_type(full_text)
    capacity, is_kit = extract_capacity_and_kit(full_text)
    freq = extract_frequency(full_text)
    form_factor = detect_form_factor(full_text)
    red_flags = detect_red_flags(full_text)
    
    result = {
        "ram_type": ram_type or "Unknown",
        "capacity_gb": capacity,
        "is_kit": is_kit,
        "frequency_mhz": freq,
        "form_factor": form_factor,
        "red_flags": red_flags,
        "is_deal": False,
        "deal_rating": "NOT_ENOUGH_DATA",
        "estimated_market_price": None,
        "ai_summary": ""
    }
    
    # Severe red flags discard deal status
    if "SERVER_ECC" in form_factor or any("дефект" in rf.lower() or "ловушка" in rf.lower() for rf in red_flags):
        result["deal_rating"] = "SUSPICIOUS"
        result["is_deal"] = False
        result["ai_summary"] = "⚠️ Осторожно: " + (red_flags[0] if red_flags else "сомнительное предложение.")
        return result

    if not price or price <= 0:
        result["deal_rating"] = "NO_PRICE"
        result["ai_summary"] = "Цена не указана или договорная."
        return result
        
    if not ram_type or not capacity:
        result["ai_summary"] = "Не удалось точно определить тип или объем памяти."
        return result

    # Check benchmark
    bench_key = (ram_type, capacity, is_kit)
    if bench_key not in BENCHMARKS:
        # Fallback approximate
        bench_key = (ram_type, capacity, False)
        
    if bench_key in BENCHMARKS:
        market_fair, good_thresh, top_thresh = BENCHMARKS[bench_key]
        result["estimated_market_price"] = market_fair
        
        # Calculate discount
        discount_pct = int(((market_fair - price) / market_fair) * 100)
        
        if price <= top_thresh:
            result["is_deal"] = True
            result["deal_rating"] = "TOP_DEAL"
            result["ai_summary"] = f"🔥 СУПЕРЦЕНА! Ниже рынка на ~{discount_pct}% (рынок ~{market_fair}₽). Стоит брать срочно!"
        elif price <= good_thresh:
            result["is_deal"] = True
            result["deal_rating"] = "GOOD_DEAL"
            result["ai_summary"] = f"⚡ Выгодная сделка! Скидка ~{discount_pct}% от средней цены (рынок ~{market_fair}₽)."
        elif price <= market_fair:
            result["deal_rating"] = "FAIR_PRICE"
            result["ai_summary"] = f"🆗 Обычная рыночная цена (рынок ~{market_fair}₽)."
        else:
            result["deal_rating"] = "BAD_DEAL"
            result["ai_summary"] = f"❌ Оверпрайс: выше средней цены на {abs(discount_pct)}%."
    else:
        result["ai_summary"] = f"{ram_type} {capacity}GB за {price}₽"
        
    return result
