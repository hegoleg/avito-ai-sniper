"""
Shared test fixtures and sample data for Avito AI Sniper test suites.
Works seamlessly with both pytest and python's built-in unittest.
"""

import os
import sys
import tempfile
import pathlib

# Ensure project root is in sys.path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Sample HTML cards for DOM and price parsing tests
HTML_CARD_STANDARD_PRICE = """
<div data-marker="item" data-item-id="449911001">
    <h3 data-marker="item-title">Kingston Fury Beast 16GB DDR4 3200MHz</h3>
    <div data-marker="item-price">
        <meta itemprop="price" content="2500">
        <strong class="styles-module-root-price-1a2b3">2 500 ₽</strong>
    </div>
    <div data-marker="item-line">г. Москва</div>
</div>
"""

HTML_CARD_DISCOUNT_OLD_PRICE = """
<div data-marker="item" data-item-id="449911002">
    <h3 data-marker="item-title">G.Skill Ripjaws V 32GB DDR4 3600MHz</h3>
    <div data-marker="item-price">
        <strong class="styles-module-root-price-1a2b3">10 500 ₽</strong>
        <span class="styles-module-root-old-price-Z4_7f">12 000 ₽</span>
    </div>
    <div data-marker="item-line">г. Санкт-Петербург</div>
</div>
"""

HTML_CARD_DISCOUNT_PERCENT = """
<div data-marker="item" data-item-id="449911003">
    <h3 data-marker="item-title">Crucial Ballistix 16GB DDR4 3200</h3>
    <div data-marker="item-price">
        <strong class="price-value">2 500 ₽</strong>
        <span class="discount-badge">-17%</span>
        <span class="old-price">3 000 ₽</span>
    </div>
    <div data-marker="item-line">г. Екатеринбург</div>
</div>
"""

HTML_CARD_META_PRICE = """
<div data-marker="item" data-item-id="449911004">
    <meta itemprop="price" content="7500">
    <h3 data-marker="item-title">Corsair Vengeance LPX 32GB DDR4</h3>
    <div data-marker="item-price">
        <span>7 500 ₽</span>
    </div>
</div>
"""

HTML_PAGE_RESERVED_ACTION = """
<html>
<body>
    <div data-marker="item-view/item-id">449911005</div>
    <div data-marker="item-view/title-info">
        <h1>Nvidia GeForce RTX 3070 8GB</h1>
    </div>
    <div data-marker="item-view/description">
        <p>Отличная видеокарта, не битая, без дефектов, родная коробка и чек в комплекте.</p>
    </div>
    <!-- Action block shows item is reserved -->
    <div data-marker="item-view/actions">
        <div data-marker="delivery-item-status">
            <span class="status-text">Товар зарезервирован</span>
        </div>
    </div>
    <div data-marker="catalog-serp" class="recommendations">
        <div data-marker="item">Рекомендация 1</div>
    </div>
</body>
</html>
"""

HTML_PAGE_RESERVED_CAROUSEL_ONLY = """
<html>
<body>
    <div data-marker="item-view/item-id">449911006</div>
    <div data-marker="item-view/title-info">
        <h1>AMD Radeon RX 6700 XT 12GB</h1>
    </div>
    <div data-marker="item-view/description">
        <p>Полностью исправна, любые проверки, артефакты отсутствуют. Без торга и брони нет.</p>
    </div>
    <!-- Listing action block is NOT reserved, delivery is available -->
    <div data-marker="item-view/actions">
        <div data-marker="delivery-item-status">
            <span>Доставка по всей России</span>
        </div>
        <button data-marker="delivery-button">Купить с доставкой</button>
    </div>
    <!-- Recommendation carousel contains another item that IS reserved -->
    <div data-marker="similar-items" class="recommendation-carousel">
        <h2>Похожие объявления</h2>
        <div data-marker="item" class="other-card">
            <span>RTX 2060 Super</span>
            <div class="delivery-status">Товар зарезервирован</div>
        </div>
        <div data-marker="item" class="other-card">
            <span>GTX 1660 Ti</span>
            <div class="badge">Заказ оформлен</div>
        </div>
    </div>
</body>
</html>
"""

HTML_PAGE_CLOSED_WARNING = """
<html>
<body>
    <div data-marker="item-view/closed-warning">
        <span>Объявление снято с публикации. Товар продан.</span>
    </div>
    <div data-marker="item-view/actions">
    </div>
</body>
</html>
"""

HTML_PAGE_ACTIVE_DELIVERY = """
<html>
<body>
    <div data-marker="item-view/item-id">449911007</div>
    <div data-marker="item-view/title-info">
        <h1>Nvidia GeForce RTX 4070 12GB</h1>
    </div>
    <div data-marker="item-view/description">
        <p>Идеальное состояние, не ремонтировалась, без дефектов, копия чека в комплекте.</p>
    </div>
    <div data-marker="item-view/actions">
        <div data-marker="delivery-item-status">
            <span>Авито Доставка активна</span>
        </div>
        <button data-marker="delivery-button">Купить с доставкой</button>
    </div>
    <div data-marker="seller-info/name">
        <span>Иван Компьютерный</span>
    </div>
    <div data-marker="seller-info/rating">
        <span>5.0 (42 отзыва)</span>
    </div>
</body>
</html>
"""


def create_temp_db_file() -> str:
    """Create a temporary database file and initialize schema."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_avito_")
    os.close(fd)
    try:
        from database import init_db
        init_db(path)
    except Exception:
        pass
    return path


def cleanup_temp_db(path: str) -> None:
    """Safely remove temporary database file and associated WAL/SHM files."""
    for p in [path, f"{path}-wal", f"{path}-shm"]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def make_mock_item(
    item_id: str = "1001",
    title: str = "Kingston DDR4 16GB",
    price: int = 2500,
    source_sort: str = "104",
    url: str = "https://avito.ru/item/1001",
    location: str = "Москва",
    description: str = "Отличная память, без дефектов, в комплекте родная коробка",
) -> dict:
    """Generate a mock item dictionary matching scraper output."""
    return {
        "id": item_id,
        "item_id": item_id,
        "title": title,
        "price": price,
        "url": url,
        "location": location,
        "source_sort": source_sort,
        "raw_description": description,
        "description": description,
    }


# Pytest fixtures if pytest is installed
try:
    import pytest

    @pytest.fixture
    def temp_db():
        """Pytest fixture yielding an initialized temporary SQLite database path."""
        path = create_temp_db_file()
        yield path
        cleanup_temp_db(path)

    @pytest.fixture
    def sample_cards():
        """Pytest fixture providing HTML card fixtures."""
        return {
            "standard": HTML_CARD_STANDARD_PRICE,
            "discount_old_price": HTML_CARD_DISCOUNT_OLD_PRICE,
            "discount_percent": HTML_CARD_DISCOUNT_PERCENT,
            "meta_price": HTML_CARD_META_PRICE,
            "reserved_action": HTML_PAGE_RESERVED_ACTION,
            "reserved_carousel_only": HTML_PAGE_RESERVED_CAROUSEL_ONLY,
            "closed": HTML_PAGE_CLOSED_WARNING,
            "active_delivery": HTML_PAGE_ACTIVE_DELIVERY,
        }

except ImportError:
    pass
