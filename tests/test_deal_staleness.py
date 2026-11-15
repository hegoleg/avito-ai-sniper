import os
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone
from database import (
    init_db,
    save_verified_deal,
    get_stale_verified_deals,
    update_verified_deal_recheck,
    deactivate_expired_verified_deals,
    cleanup_invalid_verified_deals,
    get_connection
)
from web_app import format_relative_time
from universal_sniper import SearchTarget

TEST_DB = "test_staleness.db"


@pytest.fixture(autouse=True)
def setup_teardown_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_deactivate_expired_verified_deals():
    # Insert one fresh deal and one old deal (5 days ago)
    deal_fresh = {
        "item_id": "fresh_1",
        "title": "Kingston 16GB DDR4 3200",
        "price": 3000,
        "url": "https://avito.ru/1",
        "location": "Москва"
    }
    deal_old = {
        "item_id": "old_1",
        "title": "Patriot 16GB DDR4 3200",
        "price": 3100,
        "url": "https://avito.ru/2",
        "location": "Владикавказ"
    }
    save_verified_deal(deal_fresh, query="ddr4 16gb 3200", db_path=TEST_DB)
    save_verified_deal(deal_old, query="ddr4 16gb 3200", db_path=TEST_DB)

    # Manually backdate old_1 in DB to 5 days ago
    with get_connection(TEST_DB) as conn:
        conn.execute("UPDATE verified_deals SET verified_at = datetime('now', '-5 days') WHERE item_id = 'old_1'")
        conn.commit()

    deactivated = deactivate_expired_verified_deals(max_age_days=3, db_path=TEST_DB)
    assert deactivated == 1

    with get_connection(TEST_DB) as conn:
        r_old = conn.execute("SELECT is_active FROM verified_deals WHERE item_id = 'old_1'").fetchone()
        r_fresh = conn.execute("SELECT is_active FROM verified_deals WHERE item_id = 'fresh_1'").fetchone()
        assert r_old[0] == 0
        assert r_fresh[0] == 1


def test_get_stale_verified_deals():
    deal_fresh = {
        "item_id": "fresh_2",
        "title": "Kingston 16GB DDR4 3200",
        "price": 3000,
        "url": "https://avito.ru/fresh2",
        "location": "Москва"
    }
    deal_stale = {
        "item_id": "stale_2",
        "title": "G.Skill 16GB DDR4 3200",
        "price": 3200,
        "url": "https://avito.ru/stale2",
        "location": "СПб"
    }
    save_verified_deal(deal_fresh, query="ddr4 16gb 3200", db_path=TEST_DB)
    save_verified_deal(deal_stale, query="ddr4 16gb 3200", db_path=TEST_DB)

    # Backdate stale_2 to 14 hours ago
    with get_connection(TEST_DB) as conn:
        conn.execute("UPDATE verified_deals SET verified_at = datetime('now', '-14 hours') WHERE item_id = 'stale_2'")
        conn.commit()

    stale = get_stale_verified_deals(max_age_hours=12, db_path=TEST_DB)
    assert len(stale) == 1
    assert stale[0]["item_id"] == "stale_2"


def test_update_verified_deal_recheck_alive():
    deal = {
        "item_id": "alive_1",
        "title": "Crucial 16GB DDR4 3200",
        "price": 2900,
        "url": "https://avito.ru/alive1",
        "location": "Казань"
    }
    save_verified_deal(deal, query="ddr4 16gb 3200", db_path=TEST_DB)

    # Backdate to 1 day ago
    with get_connection(TEST_DB) as conn:
        conn.execute("UPDATE verified_deals SET verified_at = datetime('now', '-1 day') WHERE item_id = 'alive_1'")
        conn.commit()

    # Re-verify with updated price
    update_verified_deal_recheck("alive_1", is_active=True, price=2800, specs={"seller_rating": "5.0"}, db_path=TEST_DB)

    with get_connection(TEST_DB) as conn:
        row = conn.execute("SELECT price, is_active, specs FROM verified_deals WHERE item_id = 'alive_1'").fetchone()
        assert row["price"] == 2800
        assert row["is_active"] == 1
        assert "5.0" in row["specs"]


def test_update_verified_deal_recheck_closed():
    deal = {
        "item_id": "closed_1",
        "title": "Patriot 16GB DDR4 3200",
        "price": 2700,
        "url": "https://avito.ru/closed1",
        "location": "Владикавказ"
    }
    save_verified_deal(deal, query="ddr4 16gb 3200", db_path=TEST_DB)

    # Mark closed
    update_verified_deal_recheck("closed_1", is_active=False, db_path=TEST_DB)

    with get_connection(TEST_DB) as conn:
        row = conn.execute("SELECT is_active FROM verified_deals WHERE item_id = 'closed_1'").fetchone()
        assert row["is_active"] == 0


def test_cleanup_invalid_verified_deals_bait_price():
    deal_bait = {
        "item_id": "bait_100",
        "title": "Patriot 16GB DDR4 3200",
        "price": 100,  # 100 rub bait / closed price
        "url": "https://avito.ru/bait100",
        "location": "Владикавказ"
    }
    save_verified_deal(deal_bait, query="ddr4 16gb 3200", db_path=TEST_DB)

    purged = cleanup_invalid_verified_deals(db_path=TEST_DB)
    assert purged == 1

    with get_connection(TEST_DB) as conn:
        row = conn.execute("SELECT is_active FROM verified_deals WHERE item_id = 'bait_100'").fetchone()
        assert row["is_active"] == 0


def test_format_relative_time():
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    ts_just_now = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    assert format_relative_time(ts_just_now) == "только что"

    ts_30_min = (now_utc - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    assert "мин назад" in format_relative_time(ts_30_min)

    ts_5_hours = (now_utc - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    assert "ч назад" in format_relative_time(ts_5_hours)

    ts_2_days = (now_utc - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    assert "д назад" in format_relative_time(ts_2_days)
