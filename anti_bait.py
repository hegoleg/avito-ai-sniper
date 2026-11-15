"""
Anti-Bait and Catalog Filter for Avito Sniper.

Detects and filters out:
1. Multi-model catalog listings ("Сборная солянка" / прайс-листы с ценой за самую дешёвую деталь).
   Example: "Ryzen 5500 / 5600 / 5600x / 5700x" with price 8,000 ₽ (8,000 is for 5500, not 5700X!).
2. Price bait & fake prices ("цена от ...", "цены в описании", "прайс в тексте", "уточняйте цену").
3. Barter / Trade-in only listings ("обмен на ...", "только обмен", "/ обмен").
4. Pawnshop & buying advertisements ("скупка", "выкуп", "купим", "куплю").
5. SEO comparison spam ("i5 12400f (аналог ryzen 5600x)", "ryzen 5600x(i5 11400f)").
"""

import re
from typing import Tuple, Optional, Set, List

# --- Delimiter-based catalog patterns in title ---
# E.g. "5500/5600", "5500, 5600", "3060/3070", "5600;5700"
SLASH_MODELS_REGEX = re.compile(
    r"\b\d{4}[a-z]?\s*[/,;\\|]\s*\d{4}",
    re.IGNORECASE
)

# E.g. "Ryzen 5/7", "R5/R7", "i5/i7", "RTX/GTX", "i3 / i5"
TIER_SLASH_REGEX = re.compile(
    r"\b(?:ryzen|r|i|core|rtx|gtx)\s*[3579]\s*[/,;\\|]\s*[3579]\b",
    re.IGNORECASE
)

# --- Hardware model extractors ---
# AMD CPUs: 1200..9950x. Exclude frequencies (e.g. "DDR4 3200" or "3200 MHz")
AMD_CPU_REGEX = re.compile(
    r"(?<!ddr[345]\s)(?<!ddr\s)\b(?:r[3579]|ryzen\s*[3579])?\s*"
    r"((?:1[2-9]00|2[6-8]00|3[1-9]00|4[1-6]00|5[5-9]00|7[5-9]00|8[4-7]00|9[6-9]00)[a-z0-9]*(?:x3d|xt|x|g)?)\b"
    r"(?!\s*(?:mhz|мгц|гц|cl\d+))",
    re.IGNORECASE
)

# Intel CPUs
INTEL_CPU_REGEX = re.compile(
    r"\b(?:i[3579]\s*-?\s*\d{4,5}[a-z]{0,2}|core\s*i[3579]|lga\s*\d{3,4})\b",
    re.IGNORECASE
)

# NVIDIA / AMD GPUs
GPU_MODELS_REGEX = re.compile(
    r"\b(?:rtx|gtx|rx)?\s*"
    r"(10[5-8]0|16[56]0|20[6-8]0|30[5-9]0|40[6-9]0|50[6-9]0|5[5-8]00|6[5-9]00|7[6-9]00)"
    r"[a-z\s]*(?:ti|super|xt|gre)?\b",
    re.IGNORECASE
)

# Motherboard multi-chipset / sockets (e.g. "am4/am5", "1151/1200/1700")
MB_MULTI_REGEX = re.compile(
    r"\b(?:am4|am5|1150|1151|1155|1200|1700|b450|b550|x570|b650|x670)\s*[/,;\\|]\s*"
    r"(?:am4|am5|1150|1151|1155|1200|1700|b450|b550|x570|b650|x670)\b",
    re.IGNORECASE
)

# RAM multiple generations (e.g. "DDR 3 DDR 4", "DDR3 / DDR4", "DDR4, DDR3L, DDR3 и DDR2")
RAM_GEN_REGEX = re.compile(
    r"\bddr\s*([2-5]l?)\b",
    re.IGNORECASE
)

# RAM mixed form factor in title (e.g. "ПК и ноутбук", "для компьютера и ноутбука", "dimm и sodimm")
RAM_MULTI_FORM_FACTOR_REGEX = re.compile(
    r"\b(?:(?:пк|компьютер\w*|системник\w*|dimm)\s*(?:и|/|,|\+)\s*(?:ноутбук\w*|ноута|sodimm|so-dimm)|"
    r"(?:ноутбук\w*|ноута|sodimm|so-dimm)\s*(?:и|/|,|\+)\s*(?:пк|компьютер\w*|системник\w*|dimm)|"
    r"для\s+(?:пк|компьютера)\s+и\s+ноутбука)\b",
    re.IGNORECASE
)

# RAM multiple capacities in title (e.g. "8gb,16gb,32gb", "8/16/32", "8gb / 16gb")
RAM_MULTI_CAPACITY_REGEX = re.compile(
    r"\b(?:4|8|16|32|64)\s*(?:gb|гб)?\s*[/,;\\|]\s*(?:4|8|16|32|64)\s*(?:gb|гб)?\b",
    re.IGNORECASE
)

# --- Bait Price Phrases (Title & Description) ---
BAIT_PRICE_PATTERNS = [
    r"\bцен(?:а|ы)\s+от\b",
    r"\bстоимость\s+от\b",
    r"\bот\s+\d{3,6}\s*(?:руб|р|₽)\b",
    r"\b(?:цена|цены|прайс|прайс-?лист)\s+(?:в\s+описании|в\s+тексте|ниже)\b",
    r"\bактуальные\s+цены\s+ниже\b",
    r"\b(?:уточняйте|уточнять)\s+(?:наличие\s*,?\s*и\s+)?цен[ыу]\b",
    r"\b(?:наличие\s*,?\s*(?:и\s+)?|цен[ыу]\s+)?уточняйте\b(?=.*?\bцен[ыу]\b)",
    r"\bцен[ыу]\s+уточняйте\b",
    r"\bцен(?:а|ы)\s+по\s+запросу\b",
    r"\bцены\s+разные\b",
    r"\bцена\s+договорная\b",
    r"\bв\s+наличии\s*[:\s]+несколько\b",
    r"\bцена\s+указана\s+за\s+(?:младший|минимальный|самый|один|одну|1)\b",
    r"\bцена\s+за\s+(?:младший|минимальный|самый|одну|1)\b",
    r"\bсписок\s+(?:процессоров|видеокарт|товаров|наличия|комплектующих)\b",
    r"\bпрайс(?:-лист)?\s*[:\n]",
    r"\bпрайс-лист\b",
    r"\bценник\s+(?:в\s+тексте|в\s+описании|ниже)\b",
]

# --- Barter & Pawnshop Patterns ---
BARTER_POSITIVE_PATTERNS = [
    r"\bтолько\s+обмен\b",
    r"\bобмен\s+на\b",
    r"\bна\s+обмен\b",
    r"\bобмен\s+(?:не\s+продажа|без\s+продажи)\b",
    r"\b(?:только\s+)?трейд-?ин\b",
    r"\bскупка\b",
    r"\bсрочный\s+выкуп\b",
    r"\bвыкуп\b",
    r"\bкупим\b",
    r"^\s*куплю\b",
    r"\bкуплю\b(?!\s+(?:комплект|процессор|видеокарту|плату))",
]

BARTER_NEGATIVE_REGEX = re.compile(
    r"\b(?:без|не|никакого)\s+обмен|\bобмен\s+(?:не\s+(?:интересует|предлагать|нужен|рассматриваю)|мимо)",
    re.IGNORECASE
)

# --- SEO Comparison Spam Patterns ---
SEO_COMPARISON_PATTERNS = [
    r"\bаналог\s+(?:ryzen|core|intel|i[3579]|rtx|gtx|rx)\b",
    r"\bлучше\s+чем\s+(?:ryzen|core|intel|i[3579]|rtx|gtx|rx)\b",
    r"\bна\s+уровне\s+(?:ryzen|core|intel|i[3579]|rtx|gtx|rx)\b",
    r"\bвместо\s+(?:ryzen|core|intel|i[3579]|rtx|gtx|rx)\b",
    r"\bсравним\s+с\s+(?:ryzen|core|intel|i[3579]|rtx|gtx|rx)\b",
]


def check_trade_or_pawnshop(title: str, text: str = "") -> Tuple[bool, str]:
    """Checks if the listing is an exchange / barter or pawnshop buying ad."""
    combined = f"{title} {text}".lower()

    # If seller explicitly says "NO EXCHANGE", do not trigger on barter
    has_negative_exchange = bool(BARTER_NEGATIVE_REGEX.search(combined))

    t_clean = title.strip().lower()

    # In title: if the word "обмен" is present (and not negative like "без обмена")
    if not has_negative_exchange:
        if re.search(r"\bобмен\b", t_clean):
            return True, "Обмен в названии"

    for p in BARTER_POSITIVE_PATTERNS:
        # If it's an exchange pattern and negative exchange is stated, skip it
        if "обмен" in p and has_negative_exchange:
            continue
        if re.search(p, combined):
            return True, f"Скупка, выкуп или обмен ({p})"

    return False, "OK"


def check_platform_clash(title: str, query: str = "") -> Tuple[bool, str]:
    """
    Checks if seller is using rival platform keywords for SEO spam.
    E.g. Searching 'Ryzen 5 5600X' but title is 'Ryzen 5600x(i5 11400f)'
    """
    if not query:
        return False, "OK"

    q_lower = query.lower()
    t_lower = title.lower()

    # Search for AMD / Ryzen -> title contains Intel Core / LGA
    if any(k in q_lower for k in ["ryzen", "am4", "am5"]) and "intel" not in q_lower:
        match = INTEL_CPU_REGEX.search(t_lower)
        if match:
            return True, f"SEO-спам / упоминание Intel ({match.group(0)}) при поиске Ryzen"

    # Search for Intel Core -> title contains AMD / Ryzen
    if any(k in q_lower for k in ["intel", "core", "12400", "13400", "12600"]) and "ryzen" not in q_lower:
        if re.search(r"\b(?:ryzen|am4|am5)\b", t_lower):
            return True, "SEO-спам / упоминание AMD при поиске Intel"

    # Search for Nvidia RTX/GTX -> title contains AMD Radeon RX
    if any(k in q_lower for k in ["rtx", "gtx", "geforce"]) and "radeon" not in q_lower and "rx" not in q_lower:
        if re.search(r"\b(?:rx\s*\d{4}|radeon)\b", t_lower):
            return True, "SEO-спам / упоминание Radeon при поиске GeForce"

    return False, "OK"


def check_multi_model_catalog(title: str, query: str = "") -> Tuple[bool, str]:
    """
    Detects if the title lists multiple distinct hardware items/tiers (catalog pricing trap).
    """
    # 1. Delimiters directly between models (e.g. "5500/5600", "5500, 5600")
    if SLASH_MODELS_REGEX.search(title):
        return True, "Сборный каталог (модели через слэш/запятую в названии)"

    # 2. Tier slashes (e.g. "Ryzen 5/7", "i5/i7")
    if TIER_SLASH_REGEX.search(title):
        return True, "Сборный каталог (несколько линеек через слэш в названии)"

    # 3. Motherboard multi-socket / multi-chipset
    if MB_MULTI_REGEX.search(title):
        return True, "Сборный каталог материнских плат (несколько сокетов/чипсетов)"

    # 4. Multiple distinct AMD CPU models
    amd_hits = AMD_CPU_REGEX.findall(title)
    if amd_hits:
        # Normalize: "5600x", "5600х", "5600" -> keep base digits or full model
        normalized_cpus = set()
        for hit in amd_hits:
            base_num = re.search(r"\d{4}", hit)
            if base_num:
                normalized_cpus.add(base_num.group(0))
        if len(normalized_cpus) >= 2:
            return True, f"Сборный список процессоров в названии: {sorted(list(normalized_cpus))}"

    # 5. Multiple distinct GPU models
    gpu_hits = GPU_MODELS_REGEX.findall(title)
    if gpu_hits:
        normalized_gpus = set()
        for hit in gpu_hits:
            base_gpu = re.search(r"\d{3,4}", hit)
            if base_gpu:
                normalized_gpus.add(base_gpu.group(0))
        if len(normalized_gpus) >= 2:
            return True, f"Сборный список видеокарт в названии: {sorted(list(normalized_gpus))}"

    # 6. Multiple distinct RAM generations (e.g. DDR3 and DDR4, DDR4 and DDR2)
    ram_gen_matches = RAM_GEN_REGEX.findall(title)
    if ram_gen_matches:
        # Standardize '3l' -> '3' for generation counting
        norm_gens = set(g.lower().replace('l', '') for g in ram_gen_matches)
        if len(norm_gens) >= 2:
            return True, f"Сборный каталог нескольких поколений памяти ({', '.join(sorted(['DDR' + g for g in norm_gens]))})"

    # 7. RAM mixed form-factors in title (ПК и ноутбук, DIMM и SODIMM)
    if RAM_MULTI_FORM_FACTOR_REGEX.search(title):
        return True, "Сборный каталог памяти (ПК и ноутбук в одном объявлении)"

    # 8. RAM multiple capacities in title (e.g. 8gb,16gb,32gb or 8/16/32)
    if RAM_MULTI_CAPACITY_REGEX.search(title):
        return True, "Сборный каталог нескольких объёмов памяти в названии"

    return False, "OK"


def check_bait_phrases(text: str) -> Tuple[bool, str]:
    """Checks for explicit bait price phrases in text (title or description)."""
    t_lower = text.lower()
    for p in BAIT_PRICE_PATTERNS:
        if re.search(p, t_lower):
            return True, f"Ложная цена / прайс-лист в тексте ({p})"

    for p in SEO_COMPARISON_PATTERNS:
        if re.search(p, t_lower):
            return True, f"SEO-сравнение в тексте ({p})"

    return False, "OK"


def check_listing_bait(title: str, snippet: str = "", query: str = "") -> Tuple[bool, str]:
    """
    Fast pre-filter for catalog search cards.
    """
    # 1. Barter / Pawnshop
    is_trade, reason = check_trade_or_pawnshop(title, snippet)
    if is_trade:
        return True, reason

    # 2. Multi-model catalog
    is_catalog, reason = check_multi_model_catalog(title, query)
    if is_catalog:
        return True, reason

    # 3. Platform clash / SEO spam in title
    is_clash, reason = check_platform_clash(title, query)
    if is_clash:
        return True, reason

    # 4. Bait phrases in title or snippet
    is_bait, reason = check_bait_phrases(f"{title} {snippet}")
    if is_bait:
        return True, reason

    return False, "OK"


def check_description_bait(combined_text: str, query: str = "") -> Tuple[bool, str]:
    """
    Deep verification for item page full description and specs.
    """
    if not combined_text:
        return False, "OK"

    # 1. Barter / Pawnshop check in full text
    is_trade, reason = check_trade_or_pawnshop("", combined_text)
    if is_trade:
        return True, reason

    # 2. Bait price phrases in full text
    is_bait, reason = check_bait_phrases(combined_text)
    if is_bait:
        return True, reason

    # 3. Detect multi-item price list bullet points in description (e.g. "- DDR3 4 Гб 1800", "- DDR3 8 Гб 2500")
    price_lines = re.findall(
        r"(?:^|\n)\s*[-*•\d\)]+\s*.*?(\d{3,6})\s*(?:руб|р|₽|\b)",
        combined_text,
        re.IGNORECASE
    )
    if len(price_lines) >= 2:
        # Check if the lines contain hardware terms
        if re.search(r"\b(?:ddr|гб|gb|продам|озу|видеокарт|ryzen|core|intel|asus|msi)\b", combined_text, re.IGNORECASE):
            return True, "Прайс-лист на несколько комплектующих в описании"

    return False, "OK"
