"""
Negation Filter Module for Avito RAM Sniper.

Implements the Two-Pass Negation Masking Architecture:
- Pass 1: Identifies and masks negated defect phrases (e.g. "не битая", "без дефектов",
  "артефакты отсутствуют", "без отвала") and legitimate packaging/proof mentions
  (e.g. "в комплекте коробка", "родная коробка", "копия чека") with a neutral token.
- Pass 2: Evaluates DEFAULT_EXCLUDES and user exclude words against the masked text,
  preventing false positives while reliably catching true defects ("битая", "на запчасти",
  "только коробка", "код 43", etc.).
"""

import re
from typing import List, Optional, Tuple

# Patterns identifying genuine defects, non-target listings, or price traps
DEFAULT_EXCLUDES: List[str] = [
    r"\bна\s+запчаст(?:и|ей)\b",
    r"\bне\s+(?:включается|стартует|работает|определяется|запускает|запускается)\b",
    r"\bне\s*рабоч(?:ая|ий|ее|ие)\b",
    r"\bнеисправн(?:ая|ый|ое|ые)\b",
    r"\bс\s+дефект(?:ом|ами)\b",
    r"\bпод\s+восстановление\b",
    r"\bбит(?:ая?|ый|ое|ые)\b",
    r"\bотвал\w*\b",
    r"\bартефакт(?:ы|ит)?\b",
    r"\bкод\s+43\b",
    r"\bкопи(?:я|и)\b",
    r"\bреплик(?:а|и)\b",
    # Strictly match box-only / packaging-only listings, never legitimate inclusion of packaging
    r"\b(?:только|пустая|одна)\s+коробк(?:а|у|и)\b",
    r"\bпрода[её]тся\s+(?:только\s+)?коробк(?:а|у|и)\b",
    r"\bкоробк(?:а|у|и)\s+без\s+(?:видеокарты|карты|процессора|платы)\b",
    r"\bпустая\s+коробка\b",
    r"\bаренд(?:а|у)\b",
    r"\bцена\s+(?:указана\s+)?за\s+(?:одну|1|каждую|одну\s+из)\s*(?:плашку|планку|шт|штуку)?\b",
    r"\bцена\s+за\s+(?:штуку|плашку|планку|1\s*шт)\b",
]

# Patterns that negate defect keywords or indicate legitimate context
NEGATION_PATTERNS: List[str] = [
    # Compound negations (e.g. "Отвала и дефектов нет") - evaluated first to prevent partial masking
    r"\b(?:отвал\w*|артефакт\w*|дефект\w*)[\s,]+и[\s,]+(?:отвал\w*|артефакт\w*|дефект\w*)[\s:—–-]+(?:отсутству\w*|нет|нету|не\s+(?:обнаружен\w*|выявлен\w*|замечен\w*))\b",
    # Preceding negative particle "не" or hyphenated "не-" (e.g. "не битая", "не-битая", "не отвал")
    r"\bне[\s-]+(?:битая?|битый?|битое?|битые?|бит|бита|отвал\w*|артефакт\w*|копи\w*|реплик\w*|под\s+восстановление)\b",
    # Preposition "без" (e.g. "без дефектов", "без артефактов", "без отвала", "без ремонта")
    r"\bбез\s+(?:дефект\w*|артефакт\w*|бит\w*|отвал\w*|ремонт\w*|проблем\w*|нюанс\w*)\b",
    # Negative pronouns "никаких / никакого / никакой"
    r"\bникак(?:их|ого|ой)\s+(?:дефект\w*|артефакт\w*|отвал\w*|проблем\w*|нюанс\w*)\b",
    # Following existence negation predicates with colons and dashes ("артефакты: отсутствуют", "дефектов — нет", "отвал: нет")
    r"\b(?:артефакт\w*|дефект\w*|отвал\w*|нюанс\w*|проблем\w*)[\s:—–-]+(?:отсутству\w*|нет|нету|не\s+(?:обнаружен\w*|выявлен\w*|замечен\w*)|исключен\w*)\b",
    # Preceding existence negation predicates with colons and dashes ("отсутствуют: дефекты", "нет — артефактов", "нет отвала")
    r"\b(?:отсутству\w*|нет|нету)[\s:—–-]+(?:артефакт\w*|дефект\w*|отвал\w*|проблем\w*|нюанс\w*)\b",
    # Legitimate packaging / original box mentions ("в комплекте коробка", "родная коробка", "с коробкой")
    r"\b(?:в\s+комплекте|полный\s+комплект|родная|оригинальная|сохранилась|есть|имеется|в\s+наличии)\s+(?:родная\s+)?коробк\w*\b",
    r"\bкоробк\w*\s+(?:в\s+комплекте|есть|сохранилась|имеется|в\s+наличии|и\s+чек|документы)\b",
    r"\bс\s+коробкой\b",
    # Legitimate proof of purchase / invoice copies with optional intervening adjectives ("копия чека", "копия гарантийного талона")
    r"\b(?:электронная\s+)?копи(?:я|и|ю)\s+(?:[а-яА-ЯёЁ]+\s+)?(?:чека|документов|гарантии|талона)\b",
]

# Patterns that negate item reservation or order in-progress claims
RESERVED_NEGATION_PATTERNS: List[str] = [
    r"\b(?:без|не|никакой|нет)\s+(?:брони|резерва)\b",
    r"\b(?:не\s+(?:в\s+резерве|зарезервирован\w*|забронирован\w*|продан\w*))\b",
    r"\b(?:бронь\s+не\s+(?:ставлю|держу))\b",
    r"\b(?:брони\s+нет)\b",
    r"\bпока\s+объявление\s+(?:висит|на\s+сайте)[^.,\n]*(?:не\s+продан\w*)",
    r"\bпродано\s+(?:более|уже|\d+)\s*(?:шт|штук|видеокарт|процессоров|комплектов|товаров)?\b",
    r"\bуже\s+продано\b",
    r"\bуспешно\s+продано\b",
]


def mask_negations(text: str) -> str:
    """
    Replaces negated defect phrases and legitimate packaging/document mentions
    with a neutral placeholder token to prevent false-positive excludes.
    """
    if not text or not isinstance(text, str):
        return ""
    masked = text.lower()
    for pat in NEGATION_PATTERNS:
        masked = re.sub(pat, " [MASKED_NEGATION] ", masked)
    return masked


def is_reserved_text(text: str) -> bool:
    """
    Checks if text indicates an item is reserved or sold, respecting negation phrases
    (e.g., 'без брони', 'не в резерве', 'пока объявление висит - не продано').
    """
    if not text or not isinstance(text, str):
        return False
    t = text.lower()
    for pat in RESERVED_NEGATION_PATTERNS:
        t = re.sub(pat, " [MASKED_NOT_RESERVED] ", t)
    return any(w in t for w in [
        "зарезервир",
        "забронир",
        "в резерве",
        "бронь",
        "продан",
        "заказ оформлен",
        "товар зарезервирован"
    ])


def check_excludes(text: str, custom_excludes: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    Two-pass exclusion check:
    1. Masks out legitimate negations and packaging phrases.
    2. Checks DEFAULT_EXCLUDES and optional custom_excludes against the masked text.

    Returns:
        (is_rejected: bool, rejection_reason: Optional[str])
    """
    if not text or not isinstance(text, str):
        return False, None

    eval_text = mask_negations(text)

    # 1. Check default excludes on masked text
    for p in DEFAULT_EXCLUDES:
        if re.search(p, eval_text):
            return True, "Дефект, запчасти, копия или ловушка цены"

    # 2. Check custom user exclude words with proper word boundaries
    if custom_excludes:
        for ew in custom_excludes:
            if not ew or not isinstance(ew, str):
                continue
            pattern = r"(?<![a-zA-Z0-9а-яА-ЯёЁ])" + re.escape(ew.lower()) + r"(?![a-zA-Z0-9а-яА-ЯёЁ])"
            if re.search(pattern, eval_text):
                return True, f"Минус-слово: '{ew}'"

    return False, None
