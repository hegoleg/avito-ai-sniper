"""
PC Builder Database & State Management.
Stores user's current PC build slots, selected items, and build templates.
"""

import sqlite3
import os
from typing import Dict, Any, List, Optional
from database import DB_PATH, get_connection

DEFAULT_SLOTS = [
    {
        "slot_id": "cpu",
        "slot_name": "Процессор (CPU)",
        "icon": "🧠",
        "query": "ryzen 5 5600x",
        "min_price": 6000,
        "max_price": 13000,
        "retail_est": 12500,
        "required_words": "5600x",
        "exclude_words": "5600g,ноутбук,кулер,дефект"
    },
    {
        "slot_id": "motherboard",
        "slot_name": "Материнская плата",
        "icon": "🎛️",
        "query": "gigabyte b550m aorus elite",
        "min_price": 6500,
        "max_price": 16000,
        "retail_est": 13500,
        "required_words": "b550m,aorus,elite",
        "exclude_words": "ds3h,дефект,неисправн"
    },
    {
        "slot_id": "gpu",
        "slot_name": "Видеокарта (GPU)",
        "icon": "🎮",
        "query": "rtx 3070",
        "min_price": 25000,
        "max_price": 36000,
        "retail_est": 48000,
        "required_words": "3070",
        "exclude_words": "3070m,mobile,коробка,кулер,дефект"
    },
    {
        "slot_id": "ram",
        "slot_name": "Оперативная память (RAM)",
        "icon": "💾",
        "query": "ddr4 16gb 3200",
        "min_price": 2500,
        "max_price": 8000,
        "retail_est": 5500,
        "required_words": "ddr4,3200",
        "exclude_words": "sodimm,ecc,reg,сервер,солянк"
    },
    {
        "slot_id": "cooler",
        "slot_name": "Кулер для процессора",
        "icon": "❄️",
        "query": "id-cooling se-224-xt",
        "min_price": 800,
        "max_price": 2500,
        "retail_est": 2300,
        "required_words": "224",
        "exclude_words": "без вертушки,сломан"
    },
    {
        "slot_id": "ssd",
        "slot_name": "Накопитель (SSD M.2)",
        "icon": "⚡",
        "query": "ssd m.2 1tb",
        "min_price": 3000,
        "max_price": 7500,
        "retail_est": 7500,
        "required_words": "1tb",
        "exclude_words": "sata,не работ,дефект"
    },
    {
        "slot_id": "psu",
        "slot_name": "Блок питания (PSU)",
        "icon": "🔌",
        "query": "блок питания 650w",
        "min_price": 2500,
        "max_price": 6000,
        "retail_est": 6500,
        "required_words": "650",
        "exclude_words": "aerocool vx,не работ,шумит"
    },
    {
        "slot_id": "case",
        "slot_name": "Корпус (Case)",
        "icon": "📦",
        "query": "корпус atx со стеклом",
        "min_price": 1500,
        "max_price": 5000,
        "retail_est": 4500,
        "required_words": "корпус",
        "exclude_words": "без стекла,мятый"
    }
]

BUILD_TEMPLATES = {
    "am4_hit": {
        "title": "🔥 Народный Хит AM4 (Ryzen 5600X + RTX 3070)",
        "description": "Лучшее соотношение цены и производительности для 1080p / 2K гейминга.",
        "slots": {
            "cpu": {"query": "ryzen 5 5600x", "min": 6000, "max": 13000, "retail": 12500, "req": "5600x", "excl": "5600g,ноутбук"},
            "motherboard": {"query": "gigabyte b550m aorus elite", "min": 6500, "max": 16000, "retail": 13500, "req": "b550m,aorus", "excl": "ds3h"},
            "gpu": {"query": "rtx 3070", "min": 25000, "max": 36000, "retail": 48000, "req": "3070", "excl": "3070m,mobile,кулер"},
            "ram": {"query": "ddr4 16gb 3200", "min": 2500, "max": 8000, "retail": 5500, "req": "ddr4,3200", "excl": "sodimm,ecc"},
            "cooler": {"query": "id-cooling se-224-xt", "min": 800, "max": 2500, "retail": 2300, "req": "224", "excl": ""},
            "ssd": {"query": "ssd m.2 1tb", "min": 3000, "max": 7500, "retail": 7500, "req": "1tb", "excl": "sata"},
            "psu": {"query": "блок питания 650w", "min": 2500, "max": 6000, "retail": 6500, "req": "650", "excl": "aerocool vx"},
            "case": {"query": "корпус atx со стеклом", "min": 1500, "max": 5000, "retail": 4500, "req": "корпус", "excl": ""}
        }
    },
    "am4_pro": {
        "title": "⚡ Мощный AM4 Гейминг (Ryzen 5700X + RTX 4060)",
        "description": "8 ядер 16 потоков + современная видеокарта с поддержкой DLSS 3.",
        "slots": {
            "cpu": {"query": "ryzen 7 5700x", "min": 8000, "max": 17000, "retail": 16000, "req": "5700x", "excl": "5700g,ноутбук"},
            "motherboard": {"query": "gigabyte b550m aorus elite", "min": 6500, "max": 16000, "retail": 13500, "req": "b550m,aorus", "excl": "ds3h"},
            "gpu": {"query": "rtx 4060", "min": 25000, "max": 36000, "retail": 41000, "req": "4060", "excl": "4060m,mobile,кулер"},
            "ram": {"query": "ddr4 32gb 3200", "min": 4500, "max": 12000, "retail": 9500, "req": "ddr4,32gb", "excl": "sodimm,ecc"},
            "cooler": {"query": "id-cooling se-224-xt", "min": 800, "max": 2500, "retail": 2300, "req": "224", "excl": ""},
            "ssd": {"query": "ssd m.2 1tb", "min": 3000, "max": 7500, "retail": 7500, "req": "1tb", "excl": "sata"},
            "psu": {"query": "блок питания 700w", "min": 3000, "max": 7000, "retail": 7500, "req": "700", "excl": "aerocool vx"},
            "case": {"query": "корпус atx со стеклом", "min": 1500, "max": 5000, "retail": 4500, "req": "корпус", "excl": ""}
        }
    },
    "budget_entry": {
        "title": "🛡️ Доступный Гейминг (Ryzen 5600 + GTX 1660 Super)",
        "description": "Минимальный бюджет на вход в киберспорт и современные игры.",
        "slots": {
            "cpu": {"query": "ryzen 5 5600", "min": 5500, "max": 10500, "retail": 10500, "req": "5600", "excl": "5600g,5600x"},
            "motherboard": {"query": "материнская плата b450m", "min": 4000, "max": 8000, "retail": 7500, "req": "b450", "excl": "дефект"},
            "gpu": {"query": "gtx 1660 super", "min": 9000, "max": 14000, "retail": 22000, "req": "1660", "excl": "кулер,артефакт"},
            "ram": {"query": "ddr4 16gb 3200", "min": 2500, "max": 7000, "retail": 5500, "req": "ddr4", "excl": "sodimm,ecc"},
            "cooler": {"query": "кулер для процессора 4 трубки", "min": 600, "max": 1800, "retail": 1800, "req": "", "excl": ""},
            "ssd": {"query": "ssd m.2 512gb", "min": 1800, "max": 4500, "retail": 4500, "req": "512", "excl": ""},
            "psu": {"query": "блок питания 500w", "min": 1800, "max": 4500, "retail": 4500, "req": "500", "excl": "vx"},
            "case": {"query": "корпус matx", "min": 1000, "max": 3500, "retail": 3500, "req": "корпус", "excl": ""}
        }
    }
}


def init_builder_tables(db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pc_build (
                slot_id TEXT PRIMARY KEY,
                slot_name TEXT NOT NULL,
                icon TEXT DEFAULT '🔧',
                target_query TEXT NOT NULL,
                min_price INTEGER,
                max_price INTEGER,
                retail_est INTEGER DEFAULT 0,
                required_words TEXT DEFAULT '',
                exclude_words TEXT DEFAULT '',
                selected_item_id TEXT,
                selected_title TEXT,
                selected_price INTEGER,
                selected_url TEXT,
                selected_location TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Seed default slots if table empty
        cur = conn.execute("SELECT count(*) as cnt FROM pc_build")
        if cur.fetchone()["cnt"] == 0:
            for s in DEFAULT_SLOTS:
                conn.execute("""
                    INSERT INTO pc_build (
                        slot_id, slot_name, icon, target_query, min_price, max_price, retail_est, required_words, exclude_words
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s["slot_id"], s["slot_name"], s["icon"], s["query"], s["min_price"], s["max_price"],
                    s["retail_est"], s["required_words"], s["exclude_words"]
                ))
            conn.commit()


def get_current_build(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    init_builder_tables(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM pc_build ORDER BY rowid ASC").fetchall()
        return [dict(r) for r in rows]


def update_slot_config(
    slot_id: str,
    target_query: str,
    min_price: Optional[int],
    max_price: Optional[int],
    required_words: str = "",
    exclude_words: str = "",
    db_path: str = DB_PATH
):
    init_builder_tables(db_path)
    with get_connection(db_path) as conn:
        conn.execute("""
            UPDATE pc_build
            SET target_query = ?, min_price = ?, max_price = ?, required_words = ?, exclude_words = ?, updated_at = CURRENT_TIMESTAMP
            WHERE slot_id = ?
        """, (target_query.strip(), min_price, max_price, required_words.strip(), exclude_words.strip(), slot_id))
        conn.commit()


def select_deal_for_slot(
    slot_id: str,
    item_id: str,
    title: str,
    price: int,
    url: str,
    location: str = "",
    db_path: str = DB_PATH
):
    init_builder_tables(db_path)
    with get_connection(db_path) as conn:
        conn.execute("""
            UPDATE pc_build
            SET selected_item_id = ?, selected_title = ?, selected_price = ?, selected_url = ?, selected_location = ?, updated_at = CURRENT_TIMESTAMP
            WHERE slot_id = ?
        """, (str(item_id), title, price, url, location, slot_id))
        conn.commit()


def clear_slot_selection(slot_id: str, db_path: str = DB_PATH):
    init_builder_tables(db_path)
    with get_connection(db_path) as conn:
        conn.execute("""
            UPDATE pc_build
            SET selected_item_id = NULL, selected_title = NULL, selected_price = NULL, selected_url = NULL, selected_location = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE slot_id = ?
        """, (slot_id,))
        conn.commit()


def reset_all_selections(db_path: str = DB_PATH):
    init_builder_tables(db_path)
    with get_connection(db_path) as conn:
        conn.execute("""
            UPDATE pc_build
            SET selected_item_id = NULL, selected_title = NULL, selected_price = NULL, selected_url = NULL, selected_location = NULL, updated_at = CURRENT_TIMESTAMP
        """)
        conn.commit()


def apply_build_template(template_id: str, db_path: str = DB_PATH) -> bool:
    if template_id not in BUILD_TEMPLATES:
        return False
    tmpl = BUILD_TEMPLATES[template_id]
    init_builder_tables(db_path)
    with get_connection(db_path) as conn:
        for slot_id, s_data in tmpl["slots"].items():
            conn.execute("""
                UPDATE pc_build
                SET target_query = ?, min_price = ?, max_price = ?, retail_est = ?, required_words = ?, exclude_words = ?,
                    selected_item_id = NULL, selected_title = NULL, selected_price = NULL, selected_url = NULL, selected_location = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE slot_id = ?
            """, (
                s_data["query"], s_data.get("min"), s_data.get("max"), s_data.get("retail", 0),
                s_data.get("req", ""), s_data.get("excl", ""), slot_id
            ))
        conn.commit()
    return True
