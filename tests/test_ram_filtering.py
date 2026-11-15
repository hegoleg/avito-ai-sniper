"""
Unit tests for RAM auto-protection, SODIMM / laptop filtering,
capacity matching, and multi-generation catalog bait detection.
"""

import pytest
from universal_sniper import SearchTarget
from anti_bait import check_listing_bait, check_description_bait
from database import cleanup_invalid_verified_deals, save_verified_deal, get_all_time_top_deals


def test_screenshot1_laptop_ram_rejection():
    """Screenshot 1: 8GB DDR4 laptop RAM must be rejected when searching for desktop 16GB."""
    target = SearchTarget(
        name="RAM",
        query="ddr4 16gb 3200",
        required_words=["ddr4", "16gb", "3200"],
        exclude_words=["sodimm", "ноутбук", "ecc"]
    )
    item = {
        "item_id": "8177696587",
        "title": "Оперативная память ddr4 8gb 3200 ноутбук",
        "price": 2500,
        "raw_description": "Купил ноутбук с 8 ГБ оперативной памяти от Kingston, но сразу заменил её на 16 ГБ",
        "is_reserved": False
    }
    ok, reason = target.quick_filter(item)
    assert not ok, f"Expected rejection, but got: {reason}"
    assert "ноутбук" in reason.lower() or "8 гб" in reason.lower() or "минус-слово" in reason.lower()

    # Deep verification check
    specs_text = "Форм-фактор: SODIMM\nОбъём одного модуля, ГБ: 8\nКоличество модулей в комплекте: 1"
    deep_ok, deep_reason = target.verify_full_details(f"{item['raw_description']}\n{specs_text}")
    assert not deep_ok, f"Expected deep rejection, but got: {deep_reason}"


def test_screenshot2_multi_catalog_bait_rejection():
    """Screenshot 2: DDR3/DDR4 'солянка' with multiple generations and bait price must be rejected."""
    target = SearchTarget(
        name="RAM",
        query="ddr4 16gb 3200"
    )
    title = "Оперативная память озу DDR 3 DDR 4 пк и ноутбук"
    desc = (
        "Оперативная память ОЗУ DDR3 и DDR4 для компьютера и ноутбука, наличие, и цены уточняйте, есть новые и б/у.\n"
        "Для ПК:\n"
        "- Оперативная память ОЗУ DDR3 4 Гб 1800\n"
        "- Оперативная память ОЗУ DDR3 8 Гб 2500"
    )
    item = {
        "item_id": "8276184757",
        "title": title,
        "price": 2500,
        "raw_description": desc,
        "is_reserved": False
    }

    # 1. Anti-bait checks
    is_bait, bait_reason = check_listing_bait(title, desc, query="ddr4 16gb 3200")
    assert is_bait, f"Expected bait detection on listing, got {bait_reason}"

    is_desc_bait, desc_reason = check_description_bait(desc, query="ddr4 16gb 3200")
    assert is_desc_bait, f"Expected bait detection on description, got {desc_reason}"

    # 2. Quick filter check
    ok, reason = target.quick_filter(item)
    assert not ok, f"Expected rejection by target, got {reason}"


def test_ram_server_ecc_rejection():
    """Server ECC RAM must be automatically rejected for standard desktop query."""
    target = SearchTarget(name="RAM", query="ddr4 16gb 3200")
    item = {
        "item_id": "8477561657",
        "title": "Оперативная память ddr4 16gb серверная самовывоз",
        "price": 2500,
        "raw_description": "ECC REG для серверов и Xeon X99",
        "is_reserved": False
    }
    ok, reason = target.quick_filter(item)
    assert not ok
    assert "серверн" in reason.lower() or "ecc" in reason.lower()


def test_ram_laptop_multipack_rejection():
    """Multi-generation laptop pack must be rejected."""
    target = SearchTarget(name="RAM", query="ddr4 16gb 3200")
    item = {
        "item_id": "3219731843",
        "title": "Память для ноутбуков DDR4, DDR3L, DDR3 и DDR2",
        "price": 2500,
        "raw_description": "Планки разного объема",
        "is_reserved": False
    }
    ok, reason = target.quick_filter(item)
    assert not ok


def test_ram_legitimate_desktop_kit_accepted():
    """Legitimate 16GB (2x8GB) DDR4 3200 kits must pass cleanly."""
    target = SearchTarget(name="RAM", query="ddr4 16gb 3200")
    item1 = {
        "item_id": "8397922769",
        "title": "Оперативная память netac ddr4 2x8gb 3200",
        "price": 7000,
        "raw_description": "Отличный комплект памяти для ПК, стоял в домашней сборке. Не битая, без дефектов.",
        "is_reserved": False
    }
    ok1, reason1 = target.quick_filter(item1)
    assert ok1, f"Expected pass, got: {reason1}"

    item2 = {
        "item_id": "8347760017",
        "title": "Patriot 16gb 2x8 Kit 3200Mhz ddr4 PC-25600",
        "price": 7499,
        "raw_description": "Продам комплект памяти 16 гб (две планки по 8).",
        "is_reserved": False
    }
    ok2, reason2 = target.quick_filter(item2)
    assert ok2, f"Expected pass, got: {reason2}"


def test_explicit_sodimm_query_allows_laptop():
    """When user explicitly asks for SODIMM / laptop, it should NOT be rejected."""
    target = SearchTarget(name="Laptop RAM", query="sodimm ddr4 16gb 3200")
    assert target.allow_sodimm is True
    item = {
        "item_id": "999111222",
        "title": "SO-DIMM DDR4 16GB 3200MHz Kingston для ноутбука",
        "price": 5000,
        "raw_description": "Новая плашка для ноутбука",
        "is_reserved": False
    }
    ok, reason = target.quick_filter(item)
    assert ok, f"Expected allow for explicit SODIMM query, got: {reason}"


def test_hyphenated_so_dimm_rejected_for_desktop():
    """Item with 'so-dimm' in title must be rejected when searching for desktop RAM."""
    target = SearchTarget(name="Desktop RAM", query="ddr4 16gb 3200")
    item = {
        "item_id": "8440046914",
        "title": "Оперативная память ddr4 16gb 3200 2x8 so-dimm",
        "price": 5000,
        "raw_description": "Две плашки для ноутбука",
        "is_reserved": False
    }
    ok, reason = target.quick_filter(item)
    assert not ok, f"Expected rejection, but passed with: {reason}"
    assert "ноутбук" in reason.lower() or "so-dimm" in reason.lower() or "sodimm" in reason.lower()


def test_damaged_parts_rejected():
    """Items damaged or sold for parts must be rejected by verify_full_details."""
    target = SearchTarget(name="Desktop RAM", query="ddr4 16gb 3200")
    text = "Оперативная память новая, DDR4 Kingbank 16 GB 3200Hz, повреждена при транспортировке, на запчасти."
    ok, reason = target.verify_full_details(text)
    assert not ok
    assert "дефект" in reason.lower() or "запчасти" in reason.lower()


def test_non_working_does_not_boot_rejected():
    """Non-working items where PC does not boot must be rejected."""
    target = SearchTarget(name="Desktop RAM", query="ddr4 16gb 3200")
    text = "НЕ РАБОЧАЯ С виду все отличная, комп не запускает Доставкой отправлю"
    ok, reason = target.verify_full_details(text)
    assert not ok
    assert "дефект" in reason.lower() or "запчасти" in reason.lower()


def test_closed_archived_listing_rejected():
    """Closed or archived listing must be rejected."""
    target = SearchTarget(name="Desktop RAM", query="ddr4 16gb 3200")
    text = "Оперативная память ddr4 16gb 3200"
    ok, reason = target.verify_full_details(text, is_closed=True)
    assert not ok
    assert "снято с публикации" in reason.lower() or "закрыто" in reason.lower()


def test_specs_sodimm_rejected_when_title_has_no_sodimm():
    """When title doesn't mention sodimm (e.g. SCY), but specs state SODIMM, deep verification must reject."""
    target = SearchTarget(name="Desktop RAM", query="ddr4 16gb 3200")
    title_and_desc = "Оперативная память scy ddr4 16gb 3200"
    specs = "Форм-фактор: SODIMM | Тактовая частота: 3200 МГц | Объем: 16 ГБ"
    ok, reason = target.verify_full_details(f"{title_and_desc}\n{specs}")
    assert not ok
    assert "sodimm" in reason.lower() or "ноутбук" in reason.lower()


def test_bsod_blue_screen_rejected():
    """RAM that throws BSOD / blue screen errors must be rejected."""
    target = SearchTarget(name="Desktop RAM", query="ddr4 16gb 3200")
    text = "Использовал пару раз. Лежит так как выдает ошибки(синий экран). Кто разбирается может и починят. 1 шт всего из комплекта."
    ok, reason = target.verify_full_details(text)
    assert not ok
    assert "дефект" in reason.lower() or "запчасти" in reason.lower()


def test_untested_no_returns_rejected():
    """Untested RAM sold 'as is' without returns must be rejected."""
    target = SearchTarget(name="Desktop RAM", query="ddr4 16gb 3200")
    text = "продаю свою оперативную память, стояла в прошлом пк, уже год лежит не знаю работает ли она, протестировать не на чем, без возврата"
    ok, reason = target.verify_full_details(text)
    assert not ok
    assert "дефект" in reason.lower() or "запчасти" in reason.lower()
