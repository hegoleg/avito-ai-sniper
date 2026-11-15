"""
Hardware Component Catalog module.
Provides a comprehensive, structured database of PC hardware chips and components:
- GPUs (by chip name, independent of vendor brands like MSI, Palit, Asus)
- CPUs (AM4, AM5, LGA1700, LGA1200)
- RAM (DDR4 / DDR5 kits by capacity and frequency)
- Motherboards (by chipset and form factor)
- SSDs (M.2 NVMe by capacity and tier)
- PSUs (by wattage and 80+ rating)
- Coolers (Towers and AIOs)
- Cases (mATX / ATX Mesh and Aquarium)

Allows browsing, instant filtering, and auto-configuring search queries, price bounds,
and optimal exclude/required words for Avito Sniper and the PC Builder Web App.
"""

import re
from typing import List, Dict, Any, Optional

HARDWARE_CATALOG: List[Dict[str, Any]] = [
    # =========================================================================
    # ВИДЕОКАРТЫ (GPUS) — ПО ЧИПАМ (NVIDIA & AMD)
    # =========================================================================
    # --- NVIDIA RTX 40 Series ---
    {
        "id": "gpu_rtx_4090",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4090",
        "name": "NVIDIA GeForce RTX 4090 24GB",
        "query": "rtx 4090",
        "min_price": 140000,
        "max_price": 220000,
        "retail_est": 230000,
        "required_words": ["4090"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт", "не вывод", "водяной блок", "бэкплейт", "подставк"],
        "specs": "24GB GDDR6X, Флагман 4K Гейминга"
    },
    {
        "id": "gpu_rtx_4080_super",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4080 Super",
        "name": "NVIDIA GeForce RTX 4080 Super 16GB",
        "query": "rtx 4080 super",
        "min_price": 85000,
        "max_price": 125000,
        "retail_est": 130000,
        "required_words": ["4080", "super"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт", "запчаст"],
        "specs": "16GB GDDR6X, Ультимативный 2K/4K"
    },
    {
        "id": "gpu_rtx_4080",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4080",
        "name": "NVIDIA GeForce RTX 4080 16GB",
        "query": "rtx 4080",
        "min_price": 75000,
        "max_price": 105000,
        "retail_est": 115000,
        "required_words": ["4080"],
        "exclude_words": ["4080 super", "4080super", "кулер", "коробка", "радиатор", "неисправн", "артефакт", "ноутбук"],
        "specs": "16GB GDDR6X, Топ для 4K"
    },
    {
        "id": "gpu_rtx_4070_ti_super",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4070 Ti Super",
        "name": "NVIDIA GeForce RTX 4070 Ti Super 16GB",
        "query": "rtx 4070 ti super",
        "min_price": 68000,
        "max_price": 95000,
        "retail_est": 102000,
        "required_words": ["4070", "ti", "super"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "16GB GDDR6X, 256-bit"
    },
    {
        "id": "gpu_rtx_4070_ti",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4070 Ti",
        "name": "NVIDIA GeForce RTX 4070 Ti 12GB",
        "query": "rtx 4070 ti",
        "min_price": 55000,
        "max_price": 78000,
        "retail_est": 85000,
        "required_words": ["4070", "ti"],
        "exclude_words": ["super", "супер", "кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "12GB GDDR6X, Идеально для 2K 144Hz"
    },
    {
        "id": "gpu_rtx_4070_super",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4070 Super",
        "name": "NVIDIA GeForce RTX 4070 Super 12GB",
        "query": "rtx 4070 super",
        "min_price": 50000,
        "max_price": 70000,
        "retail_est": 76000,
        "required_words": ["4070", "super"],
        "exclude_words": ["ti", "кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "12GB GDDR6X, Хит 2024–2026"
    },
    {
        "id": "gpu_rtx_4070",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4070",
        "name": "NVIDIA GeForce RTX 4070 12GB",
        "query": "rtx 4070",
        "min_price": 44000,
        "max_price": 62000,
        "retail_est": 68000,
        "required_words": ["4070"],
        "exclude_words": ["super", "супер", "ti", "кулер", "коробка", "радиатор", "неисправн", "артефакт", "4070m"],
        "specs": "12GB GDDR6X, Энергоэффективная 2K карта"
    },
    {
        "id": "gpu_rtx_4060_ti",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4060 Ti",
        "name": "NVIDIA GeForce RTX 4060 Ti (8GB / 16GB)",
        "query": "rtx 4060 ti",
        "min_price": 32000,
        "max_price": 48000,
        "retail_est": 52000,
        "required_words": ["4060", "ti"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт", "4060m"],
        "specs": "8GB / 16GB GDDR6, DLSS 3 Frame Gen"
    },
    {
        "id": "gpu_rtx_4060",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 40",
        "chip": "RTX 4060",
        "name": "NVIDIA GeForce RTX 4060 8GB",
        "query": "rtx 4060",
        "min_price": 24000,
        "max_price": 36000,
        "retail_est": 39000,
        "required_words": ["4060"],
        "exclude_words": ["ti", "4060m", "4060 m", "mobile", "мобайл", "кулер", "коробка", "радиатор", "неисправн"],
        "specs": "8GB GDDR6, Самая популярная карта в Steam"
    },

    # --- NVIDIA RTX 30 Series ---
    {
        "id": "gpu_rtx_3080_ti",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 30",
        "chip": "RTX 3080 Ti",
        "name": "NVIDIA GeForce RTX 3080 Ti 12GB",
        "query": "rtx 3080 ti",
        "min_price": 38000,
        "max_price": 54000,
        "retail_est": 65000,
        "required_words": ["3080", "ti"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт", "3080m"],
        "specs": "12GB GDDR6X, Мощь уровня RTX 4070"
    },
    {
        "id": "gpu_rtx_3080",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 30",
        "chip": "RTX 3080",
        "name": "NVIDIA GeForce RTX 3080 10GB",
        "query": "rtx 3080",
        "min_price": 32000,
        "max_price": 46000,
        "retail_est": 55000,
        "required_words": ["3080"],
        "exclude_words": ["ti", "кулер", "коробка", "радиатор", "неисправн", "артефакт", "3080m"],
        "specs": "10GB GDDR6X, Отличный 2K гейминг"
    },
    {
        "id": "gpu_rtx_3070_ti",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 30",
        "chip": "RTX 3070 Ti",
        "name": "NVIDIA GeForce RTX 3070 Ti 8GB",
        "query": "rtx 3070 ti",
        "min_price": 28000,
        "max_price": 39000,
        "retail_est": 48000,
        "required_words": ["3070", "ti"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт", "3070m"],
        "specs": "8GB GDDR6X, Быстрая память"
    },
    {
        "id": "gpu_rtx_3070",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 30",
        "chip": "RTX 3070",
        "name": "NVIDIA GeForce RTX 3070 8GB",
        "query": "rtx 3070",
        "min_price": 24000,
        "max_price": 35000,
        "retail_est": 44000,
        "required_words": ["3070"],
        "exclude_words": ["ti", "3070m", "3070 m", "mobile", "мобайл", "ноутбук", "кулер", "коробка", "радиатор", "неисправн"],
        "specs": "8GB GDDR6, Народный топ для 1440p"
    },
    {
        "id": "gpu_rtx_3060_ti",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 30",
        "chip": "RTX 3060 Ti",
        "name": "NVIDIA GeForce RTX 3060 Ti 8GB",
        "query": "rtx 3060 ti",
        "min_price": 20000,
        "max_price": 29000,
        "retail_est": 38000,
        "required_words": ["3060", "ti"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт", "3060m"],
        "specs": "8GB GDDR6/GDDR6X, Быстрее обычной 3060 на 30%"
    },
    {
        "id": "gpu_rtx_3060_12gb",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 30",
        "chip": "RTX 3060 12GB",
        "name": "NVIDIA GeForce RTX 3060 12GB",
        "query": "rtx 3060 12gb",
        "min_price": 18000,
        "max_price": 26000,
        "retail_est": 33000,
        "required_words": ["3060", "12gb"],
        "exclude_words": ["ti", "3060m", "mobile", "ноутбук", "кулер", "коробка", "радиатор", "неисправн"],
        "specs": "12GB GDDR6, Большой объем VRAM"
    },

    # --- NVIDIA Budget & GTX ---
    {
        "id": "gpu_rtx_2060_super",
        "category": "gpu",
        "subcategory": "NVIDIA RTX 20",
        "chip": "RTX 2060 Super",
        "name": "NVIDIA GeForce RTX 2060 Super 8GB",
        "query": "rtx 2060 super",
        "min_price": 13000,
        "max_price": 20000,
        "retail_est": 26000,
        "required_words": ["2060", "super"],
        "exclude_words": ["кулер", "коробка", "неисправн", "артефакт"],
        "specs": "8GB GDDR6, Трассировка и DLSS за малые деньги"
    },
    {
        "id": "gpu_gtx_1660_super",
        "category": "gpu",
        "subcategory": "NVIDIA GTX",
        "chip": "GTX 1660 Super",
        "name": "NVIDIA GeForce GTX 1660 Super 6GB",
        "query": "gtx 1660 super",
        "min_price": 8500,
        "max_price": 14000,
        "retail_est": 21000,
        "required_words": ["1660", "super"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "6GB GDDR6, Идеал для Full HD киберспорта"
    },

    # --- AMD Radeon RX 7000 & 6000 ---
    {
        "id": "gpu_rx_7800_xt",
        "category": "gpu",
        "subcategory": "AMD Radeon RX 7000",
        "chip": "RX 7800 XT",
        "name": "AMD Radeon RX 7800 XT 16GB",
        "query": "rx 7800 xt",
        "min_price": 45000,
        "max_price": 63000,
        "retail_est": 69000,
        "required_words": ["7800", "xt"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "16GB GDDR6, Конкурент RTX 4070"
    },
    {
        "id": "gpu_rx_7700_xt",
        "category": "gpu",
        "subcategory": "AMD Radeon RX 7000",
        "chip": "RX 7700 XT",
        "name": "AMD Radeon RX 7700 XT 12GB",
        "query": "rx 7700 xt",
        "min_price": 38000,
        "max_price": 52000,
        "retail_est": 58000,
        "required_words": ["7700", "xt"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "12GB GDDR6, 1440p Gaming"
    },
    {
        "id": "gpu_rx_6700_xt",
        "category": "gpu",
        "subcategory": "AMD Radeon RX 6000",
        "chip": "RX 6700 XT",
        "name": "AMD Radeon RX 6700 XT 12GB",
        "query": "rx 6700 xt",
        "min_price": 21000,
        "max_price": 31000,
        "retail_est": 38000,
        "required_words": ["6700", "xt"],
        "exclude_words": ["кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "12GB GDDR6, Лучший бюджетный выбор для 2K"
    },
    {
        "id": "gpu_rx_6600",
        "category": "gpu",
        "subcategory": "AMD Radeon RX 6000",
        "chip": "RX 6600",
        "name": "AMD Radeon RX 6600 8GB",
        "query": "rx 6600",
        "min_price": 13000,
        "max_price": 19000,
        "retail_est": 25000,
        "required_words": ["6600"],
        "exclude_words": ["xt", "кулер", "коробка", "радиатор", "неисправн", "артефакт"],
        "specs": "8GB GDDR6, Холодная и экономичная для 1080p"
    },

    # =========================================================================
    # ПРОЦЕССОРЫ (CPUS) — ПО ЧИПАМ / МОДЕЛЯМ (AMD & INTEL)
    # =========================================================================
    # --- AMD AM5 (Современная платформа) ---
    {
        "id": "cpu_ryzen_7800x3d",
        "category": "cpu",
        "subcategory": "AMD Socket AM5",
        "chip": "Ryzen 7 7800X3D",
        "name": "AMD Ryzen 7 7800X3D (8C/16T, 3D V-Cache)",
        "query": "ryzen 7 7800x3d",
        "min_price": 32000,
        "max_price": 48000,
        "retail_est": 52000,
        "required_words": ["7800x3d"],
        "exclude_words": ["ноутбук", "не работ", "дефект", "кулер", "коробка", "погнут"],
        "specs": "Socket AM5, Абсолютный игровой царь"
    },
    {
        "id": "cpu_ryzen_7600",
        "category": "cpu",
        "subcategory": "AMD Socket AM5",
        "chip": "Ryzen 5 7600",
        "name": "AMD Ryzen 5 7600 (6C/12T, 5.1GHz)",
        "query": "ryzen 5 7600",
        "min_price": 13000,
        "max_price": 19000,
        "retail_est": 21000,
        "required_words": ["7600"],
        "exclude_words": ["7600x", "ноутбук", "не работ", "дефект", "кулер", "коробка"],
        "specs": "Socket AM5, Встроенная графика RDNA2"
    },
    {
        "id": "cpu_ryzen_7500f",
        "category": "cpu",
        "subcategory": "AMD Socket AM5",
        "chip": "Ryzen 5 7500F",
        "name": "AMD Ryzen 5 7500F (6C/12T, 5.0GHz)",
        "query": "ryzen 5 7500f",
        "min_price": 10000,
        "max_price": 15000,
        "retail_est": 16500,
        "required_words": ["7500f"],
        "exclude_words": ["ноутбук", "не работ", "дефект", "кулер", "коробка", "погнут"],
        "specs": "Socket AM5, Главный народный хит нового поколения"
    },

    # --- AMD AM4 (Народная платформа) ---
    {
        "id": "cpu_ryzen_5700x3d",
        "category": "cpu",
        "subcategory": "AMD Socket AM4",
        "chip": "Ryzen 7 5700X3D",
        "name": "AMD Ryzen 7 5700X3D (8C/16T, 3D V-Cache)",
        "query": "ryzen 7 5700x3d",
        "min_price": 13500,
        "max_price": 20000,
        "retail_est": 22000,
        "required_words": ["5700x3d"],
        "exclude_words": ["ноутбук", "не работ", "дефект", "кулер", "коробка", "погнут"],
        "specs": "Socket AM4, Лучший апгрейд для AM4"
    },
    {
        "id": "cpu_ryzen_5700x",
        "category": "cpu",
        "subcategory": "AMD Socket AM4",
        "chip": "Ryzen 7 5700X",
        "name": "AMD Ryzen 7 5700X (8C/16T, 4.6GHz)",
        "query": "ryzen 7 5700x",
        "min_price": 8500,
        "max_price": 15000,
        "retail_est": 16000,
        "required_words": ["5700x"],
        "exclude_words": ["5700g", "5700x3d", "ноутбук", "не работ", "дефект", "кулер"],
        "specs": "Socket AM4, 8 ядер 65W"
    },
    {
        "id": "cpu_ryzen_5600x",
        "category": "cpu",
        "subcategory": "AMD Socket AM4",
        "chip": "Ryzen 5 5600X",
        "name": "AMD Ryzen 5 5600X (6C/12T, 4.6GHz)",
        "query": "ryzen 5 5600x",
        "min_price": 6000,
        "max_price": 12000,
        "retail_est": 13500,
        "required_words": ["5600x"],
        "exclude_words": ["5600g", "ноутбук", "не работ", "дефект", "кулер", "погнут"],
        "specs": "Socket AM4, Народная классика"
    },
    {
        "id": "cpu_ryzen_5600",
        "category": "cpu",
        "subcategory": "AMD Socket AM4",
        "chip": "Ryzen 5 5600",
        "name": "AMD Ryzen 5 5600 (6C/12T, 4.4GHz)",
        "query": "ryzen 5 5600",
        "min_price": 5500,
        "max_price": 10500,
        "retail_est": 11500,
        "required_words": ["5600"],
        "exclude_words": ["5600x", "5600g", "ноутбук", "не работ", "дефект", "кулер"],
        "specs": "Socket AM4, Оптимальный бюджетный 6-ядерник"
    },
    {
        "id": "cpu_ryzen_5500",
        "category": "cpu",
        "subcategory": "AMD Socket AM4",
        "chip": "Ryzen 5 5500",
        "name": "AMD Ryzen 5 5500 (6C/12T, 4.2GHz)",
        "query": "ryzen 5 5500",
        "min_price": 4500,
        "max_price": 8000,
        "retail_est": 9000,
        "required_words": ["5500"],
        "exclude_words": ["ноутбук", "не работ", "дефект", "кулер"],
        "specs": "Socket AM4, Ультрабюджетный 6 ядер"
    },

    # --- Intel LGA1700 (12–14 поколение) ---
    {
        "id": "cpu_intel_13600k",
        "category": "cpu",
        "subcategory": "Intel LGA1700",
        "chip": "Core i5 13600K",
        "name": "Intel Core i5 13600K / 13600KF (14C/20T)",
        "query": "i5 13600k",
        "min_price": 18000,
        "max_price": 28000,
        "retail_est": 32000,
        "required_words": ["13600k"],
        "exclude_words": ["ноутбук", "не работ", "дефект", "кулер", "коробка"],
        "specs": "Socket LGA1700, 6P + 8E ядер"
    },
    {
        "id": "cpu_intel_12400f",
        "category": "cpu",
        "subcategory": "Intel LGA1700",
        "chip": "Core i5 12400F",
        "name": "Intel Core i5 12400F (6C/12T, 4.4GHz)",
        "query": "i5 12400f",
        "min_price": 6500,
        "max_price": 11500,
        "retail_est": 12800,
        "required_words": ["12400f"],
        "exclude_words": ["ноутбук", "не работ", "дефект", "кулер", "коробка"],
        "specs": "Socket LGA1700, Народный Intel процессор"
    },
    {
        "id": "cpu_intel_12100f",
        "category": "cpu",
        "subcategory": "Intel LGA1700",
        "chip": "Core i3 12100F",
        "name": "Intel Core i3 12100F (4C/8T, 4.3GHz)",
        "query": "i3 12100f",
        "min_price": 4000,
        "max_price": 7500,
        "retail_est": 8500,
        "required_words": ["12100f"],
        "exclude_words": ["ноутбук", "не работ", "дефект", "кулер"],
        "specs": "Socket LGA1700, Бюджетный топ для игр"
    },

    # =========================================================================
    # ОПЕРАТИВНАЯ ПАМЯТЬ (RAM) — ПО СТАНДАРТУ, ОБЪЕМУ И ЧАСТОТЕ
    # =========================================================================
    {
        "id": "ram_ddr5_32gb_6000",
        "category": "ram",
        "subcategory": "DDR5",
        "chip": "DDR5 32GB (2x16) 6000MHz",
        "name": "Комплект DDR5 32GB (2x16GB) 6000MHz CL30-36",
        "query": "ddr5 32gb 6000",
        "min_price": 6500,
        "max_price": 13000,
        "retail_est": 14000,
        "required_words": ["ddr5", "32gb", "6000"],
        "exclude_words": ["sodimm", "ноутбук", "ecc", "reg", "сервер", "одна плашка", "1 шт"],
        "specs": "DDR5 DIMM, Оптимальная частота для AM5 / LGA1700"
    },
    {
        "id": "ram_ddr4_32gb_3200",
        "category": "ram",
        "subcategory": "DDR4",
        "chip": "DDR4 32GB (2x16) 3200MHz",
        "name": "Комплект DDR4 32GB (2x16GB) 3200MHz",
        "query": "ddr4 32gb 3200",
        "min_price": 4500,
        "max_price": 9500,
        "retail_est": 9500,
        "required_words": ["ddr4", "32gb", "3200"],
        "exclude_words": ["sodimm", "ноутбук", "ecc", "reg", "сервер", "x99", "xeon", "atermiter"],
        "specs": "DDR4 DIMM, Запас под любые современные игры"
    },
    {
        "id": "ram_ddr4_16gb_3200",
        "category": "ram",
        "subcategory": "DDR4",
        "chip": "DDR4 16GB (2x8) 3200MHz",
        "name": "Комплект DDR4 16GB (2x8GB) 3200MHz",
        "query": "ddr4 16gb 3200",
        "min_price": 2200,
        "max_price": 5000,
        "retail_est": 5200,
        "required_words": ["ddr4", "16gb", "3200"],
        "exclude_words": ["sodimm", "ноутбук", "ecc", "reg", "сервер", "x99", "xeon", "солянк"],
        "specs": "DDR4 DIMM, Базовый золотой стандарт"
    },

    # =========================================================================
    # МАТЕРИНСКИЕ ПЛАТЫ (MOTHERBOARDS) — ПО ЧИПСЕТАМ
    # =========================================================================
    {
        "id": "mb_am5_b650m",
        "category": "motherboard",
        "subcategory": "Socket AM5",
        "chip": "B650M",
        "name": "Материнская плата B650M (mATX, AM5)",
        "query": "b650m",
        "min_price": 8000,
        "max_price": 16000,
        "retail_est": 16500,
        "required_words": ["b650m"],
        "exclude_words": ["сокет сломан", "не работ", "дефект", "гнут", "на запчасти"],
        "specs": "AM5, DDR5, PCIe 4.0/5.0 M.2"
    },
    {
        "id": "mb_am4_b550m",
        "category": "motherboard",
        "subcategory": "Socket AM4",
        "chip": "B550M",
        "name": "Материнская плата B550M (mATX, AM4)",
        "query": "материнская плата b550m",
        "min_price": 5500,
        "max_price": 13000,
        "retail_est": 12500,
        "required_words": ["b550m"],
        "exclude_words": ["сокет сломан", "неисправн", "дефект", "гнут"],
        "specs": "AM4, PCIe 4.0 для GPU и M.2 SSD"
    },
    {
        "id": "mb_am4_b450m",
        "category": "motherboard",
        "subcategory": "Socket AM4",
        "chip": "B450M",
        "name": "Материнская плата B450M (mATX, AM4)",
        "query": "материнская плата b450m",
        "min_price": 3500,
        "max_price": 7500,
        "retail_est": 7500,
        "required_words": ["b450m"],
        "exclude_words": ["неисправн", "дефект", "сломан", "запчаст"],
        "specs": "AM4, Народный чипсет для Ryzen 3000/5000"
    },
    {
        "id": "mb_lga1700_b760m",
        "category": "motherboard",
        "subcategory": "Intel LGA1700",
        "chip": "B760M",
        "name": "Материнская плата B760M (LGA1700)",
        "query": "материнская плата b760m",
        "min_price": 7500,
        "max_price": 16000,
        "retail_est": 15000,
        "required_words": ["b760m"],
        "exclude_words": ["ножки погнуты", "сокет", "не работ", "дефект"],
        "specs": "LGA1700, Поддержка Intel 12/13/14 gen"
    },
    {
        "id": "mb_lga1700_h610m",
        "category": "motherboard",
        "subcategory": "Intel LGA1700",
        "chip": "H610M",
        "name": "Материнская плата H610M (LGA1700)",
        "query": "материнская плата h610m",
        "min_price": 4000,
        "max_price": 7500,
        "retail_est": 7800,
        "required_words": ["h610m"],
        "exclude_words": ["сокет", "дефект", "не работ"],
        "specs": "LGA1700, Базовая плата для i3-12100F / i5-12400F"
    },

    # =========================================================================
    # НАКОПИТЕЛИ (SSDS M.2 NVME)
    # =========================================================================
    {
        "id": "ssd_nvme_2tb",
        "category": "ssd",
        "subcategory": "M.2 NVMe SSD",
        "chip": "M.2 NVMe 2TB",
        "name": "Накопитель SSD M.2 NVMe 2TB (PCIe 4.0)",
        "query": "ssd m.2 2tb",
        "min_price": 6500,
        "max_price": 14000,
        "retail_est": 15000,
        "required_words": ["2tb"],
        "exclude_words": ["sata", "hdd", "не работ", "битые сектора", "дефект"],
        "specs": "M.2 2280, Объем 2000 ГБ"
    },
    {
        "id": "ssd_nvme_1tb",
        "category": "ssd",
        "subcategory": "M.2 NVMe SSD",
        "chip": "M.2 NVMe 1TB",
        "name": "Накопитель SSD M.2 NVMe 1TB (PCIe 3.0 / 4.0)",
        "query": "ssd m.2 1tb",
        "min_price": 3200,
        "max_price": 7500,
        "retail_est": 7800,
        "required_words": ["1tb"],
        "exclude_words": ["sata", "hdd", "не работ", "дефект"],
        "specs": "M.2 2280, Золотой стандарт для ОС и игр"
    },
    {
        "id": "ssd_nvme_512gb",
        "category": "ssd",
        "subcategory": "M.2 NVMe SSD",
        "chip": "M.2 NVMe 500GB-512GB",
        "name": "Накопитель SSD M.2 NVMe 500GB / 512GB",
        "query": "ssd m.2 512gb",
        "min_price": 1800,
        "max_price": 4000,
        "retail_est": 4500,
        "required_words": ["512gb"],
        "exclude_words": ["sata", "hdd", "не работ"],
        "specs": "M.2 2280, Быстрый системный диск"
    },

    # =========================================================================
    # БЛОКИ ПИТАНИЯ (PSUS) — ПО МОЩНОСТИ
    # =========================================================================
    {
        "id": "psu_750w_gold",
        "category": "psu",
        "subcategory": "Блоки питания",
        "chip": "Блок питания 750W-850W Gold",
        "name": "Блок питания 750W / 850W (80+ Gold)",
        "query": "блок питания 750w gold",
        "min_price": 4500,
        "max_price": 9500,
        "retail_est": 11000,
        "required_words": ["750w"],
        "exclude_words": ["aerocool vx", "не работ", "шумит", "пищит", "дефект"],
        "specs": "750W 80+ Gold, С запасом под RTX 3080 / 4070 / 4080"
    },
    {
        "id": "psu_650w",
        "category": "psu",
        "subcategory": "Блоки питания",
        "chip": "Блок питания 650W",
        "name": "Блок питания 650W (80+ Bronze / Gold)",
        "query": "блок питания 650w",
        "min_price": 2800,
        "max_price": 6000,
        "retail_est": 6800,
        "required_words": ["650w"],
        "exclude_words": ["aerocool vx", "vx", "не работ", "дефект"],
        "specs": "650W, Оптимально для RTX 3060/3070/4060"
    },
    {
        "id": "psu_500w",
        "category": "psu",
        "subcategory": "Блоки питания",
        "chip": "Блок питания 500W-550W",
        "name": "Блок питания 500W / 550W (80+ Bronze)",
        "query": "блок питания 500w",
        "min_price": 1800,
        "max_price": 4000,
        "retail_est": 4500,
        "required_words": ["500w"],
        "exclude_words": ["vx", "aerocool", "не работ"],
        "specs": "500W, Бюджетные сборки"
    },

    # =========================================================================
    # КУЛЕРЫ И СЖО (COOLING)
    # =========================================================================
    {
        "id": "cooler_tower_4pipes",
        "category": "cooler",
        "subcategory": "Кулеры CPU",
        "chip": "Кулер 4 трубки (SE-224-XT / AG400)",
        "name": "Башенный кулер 4 теплотрубки (180W-220W)",
        "query": "кулер se-224-xt",
        "min_price": 800,
        "max_price": 2400,
        "retail_est": 2500,
        "required_words": ["224"],
        "exclude_words": ["без вертушки", "сломан", "погнут"],
        "specs": "180W TDP, 120mm PWM вертушка"
    },
    {
        "id": "cooler_aio_240",
        "category": "cooler",
        "subcategory": "СЖО",
        "chip": "СЖО 240мм (Водянка)",
        "name": "Система жидкостного охлаждения 240мм (СЖО)",
        "query": "водяное охлаждение 240",
        "min_price": 2500,
        "max_price": 6500,
        "retail_est": 7500,
        "required_words": ["240"],
        "exclude_words": ["течет", "протечка", "не качает", "помпа сломана"],
        "specs": "240mm Радиатор, 2x120mm вентилятора"
    },

    # =========================================================================
    # КОРПУСА (CASES)
    # =========================================================================
    {
        "id": "case_mesh_glass",
        "category": "case",
        "subcategory": "Корпуса",
        "chip": "Корпус ATX/mATX Mesh + Стекло",
        "name": "Корпус с сетчатой панелью (Mesh) и закаленным стеклом",
        "query": "корпус mesh закаленное стекло",
        "min_price": 1800,
        "max_price": 5500,
        "retail_est": 5200,
        "required_words": ["корпус"],
        "exclude_words": ["без стекла", "мятый", "разбито"],
        "specs": "Отличная продуваемость и пылевые фильтры"
    },
    {
        "id": "case_aquarium",
        "category": "case",
        "subcategory": "Корпуса",
        "chip": "Корпус Аквариум (Панорамный)",
        "name": "Корпус-аквариум с панорамным стеклом",
        "query": "корпус аквариум",
        "min_price": 2500,
        "max_price": 7500,
        "retail_est": 8000,
        "required_words": ["аквариум"],
        "exclude_words": ["для рыбок", "рыбки", "разбит"],
        "specs": "Без угловой стойки, панорамный обзор 270°"
    }
]


def get_all_categories() -> List[Dict[str, str]]:
    """Returns unique component categories with icons and Russian labels."""
    return [
        {"id": "gpu", "name": "Видеокарты (GPU)", "icon": "🎮"},
        {"id": "cpu", "name": "Процессоры (CPU)", "icon": "🧠"},
        {"id": "ram", "name": "Оперативная память", "icon": "💾"},
        {"id": "motherboard", "name": "Материнские платы", "icon": "🎛️"},
        {"id": "ssd", "name": "Накопители (SSD M.2)", "icon": "⚡"},
        {"id": "psu", "name": "Блоки питания (PSU)", "icon": "🔌"},
        {"id": "cooler", "name": "Кулеры и СЖО", "icon": "❄️"},
        {"id": "case", "name": "Корпуса", "icon": "📦"},
    ]


def search_catalog(
    query: str = "",
    category: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Searches hardware catalog by chip keyword and optional category filter.
    Case-insensitive, normalizes spaces and letter 'х/x'.
    """
    q_clean = query.strip().lower()
    q_clean = re.sub(r'(\d+)\s*[хx]\b', r'\1x', q_clean)
    tokens = [t for t in re.findall(r'[a-zA-Z0-9а-яА-ЯёЁ]+', q_clean) if len(t) > 0]

    results = []
    for item in HARDWARE_CATALOG:
        # Category filter
        if category and category.lower() != "all" and item.get("category") != category.lower():
            continue

        if not tokens:
            results.append(item)
            continue

        # Match tokens against chip, name, query, subcategory
        searchable_text = f"{item['chip']} {item['name']} {item['query']} {item.get('subcategory', '')}".lower()
        searchable_text = re.sub(r'(\d+)\s*[хx]\b', r'\1x', searchable_text)

        if all(token in searchable_text for token in tokens):
            results.append(item)

    return results[:limit]


def get_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    """Finds an exact catalog item by its ID."""
    for it in HARDWARE_CATALOG:
        if it["id"] == item_id:
            return it
    return None
