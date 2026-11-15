"""
Avito RAM Sniper - Main Entry Point & Daemon
Monitors Avito for RAM deals, analyzes listings with AI, and sends alerts to Telegram.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime

# Ensure utf-8 output in Windows consoles
sys.stdout.reconfigure(encoding="utf-8")

from config import load_config
from database import init_db, is_item_seen, save_listing, mark_notified, get_stats
from scraper import AvitoScraper
from ai_analyzer import AIAnalyzer
from notifier import TelegramNotifier

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AvitoSniper")


async def run_single_scan(config, scraper, analyzer, notifier):
    """Executes a single scan cycle."""
    logger.info("--- Начинаем сканирование новых объявлений по ОЗУ ---")
    items = await scraper.scrape_new_listings(max_items=35)
    
    if not items:
        logger.info("Новых объявлений не найдено или сработала защита.")
        return 0

    new_count = 0
    deals_count = 0

    for item in items:
        item_id = item["item_id"]
        
        # Check if already seen
        if is_item_seen(item_id):
            continue
            
        new_count += 1
        title = item["title"]
        price = item["price"]
        desc = item["raw_description"]
        location = item["location"]
        
        logger.info("Анализ объявления [%s]: '%s' | %s ₽", item_id, title, price)
        
        # Analyze with AI / Heuristics
        analysis = analyzer.analyze(title, price, desc, location)
        
        # Merge analysis results into item dict
        item.update(analysis)
        
        is_deal = item.get("is_deal", False)
        if is_deal:
            deals_count += 1
            logger.info("🔥 НАЙДЕНА ВЫГОДНАЯ СДЕЛКА! %s (%s)", title, item.get("ai_summary"))
            # Send notification
            sent = notifier.send_deal_alert(item)
            item["notified"] = 1 if sent else 0
        else:
            item["notified"] = 0
            
        # Save to database
        save_listing(item)

    logger.info(
        "--- Сканирование завершено: проверено новых %d, найдено выгодных %d ---",
        new_count, deals_count
    )
    return deals_count


async def run_loop(config, scraper, analyzer, notifier):
    """Runs continuous monitoring loop."""
    interval_sec = max(60, config.poll_interval_minutes * 60)
    logger.info("Запуск демона мониторинга. Интервал проверки: каждые %d минут.", config.poll_interval_minutes)
    
    try:
        while True:
            try:
                await run_single_scan(config, scraper, analyzer, notifier)
            except Exception as e:
                logger.error("Ошибка во время цикла сканирования: %s", e)
                
            logger.info("Ожидание следующего цикла (%d сек)... Нажмите Ctrl+C для остановки.", interval_sec)
            await asyncio.sleep(interval_sec)
    except asyncio.CancelledError:
        logger.info("Мониторинг остановлен пользователем.")


async def run_setup(config):
    """Opens visible browser to pass captcha or log in."""
    from setup_session import setup_session
    await setup_session()


def run_test_ai(analyzer):
    """Tests AI / Heuristic analysis on tricky test cases."""
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ АНАЛИЗА ИИ (RAM SNIPER)")
    print("=" * 60)
    
    test_cases = [
        {
            "title": "Kingston Fury Beast DDR4 16GB (2x8) 3200MHz",
            "price": 1950,
            "desc": "Полностью рабочий комплект, стоял в домашнем ПК, продаю в связи с апгрейдом.",
            "location": "Москва"
        },
        {
            "title": "Оперативная память 32Gb DDR4 для сервера",
            "price": 1800,
            "desc": "Серверная память Samsung 32gb 2400 ECC REG для материнок x99 Xeon.",
            "location": "Екатеринбург"
        },
        {
            "title": "Kingston Fury DDR4 32GB комплект",
            "price": 2500,
            "desc": "Комплект 32гб (2 планки по 16гб), цена указана за одну плашку 16гб!",
            "location": "Новосибирск"
        },
        {
            "title": "G.Skill Trident Z5 RGB DDR5 32GB (2x16GB) 6400MHz",
            "price": 5900,
            "desc": "Топовая скоростная память, тайминги CL32, чипы Hynix A-die, состояние идеальное.",
            "location": "Санкт-Петербург"
        },
        {
            "title": "Corsair Vengeance LPX DDR4 16GB",
            "price": 500,
            "desc": "После сильного скачка напряжения не стартует, выдает синий экран, продаю на запчасти.",
            "location": "Казань"
        }
    ]
    
    for case in test_cases:
        res = analyzer.analyze(case["title"], case["price"], case["desc"], case["location"])
        print(f"\n[Кейс] {case['title']} — {case['price']} ₽")
        print(f"  • Вердикт:   {res.get('deal_rating')}")
        print(f"  • Сделка:    {'ДА (БРАТЬ)' if res.get('is_deal') else 'НЕТ'}")
        print(f"  • Резюме ИИ: {res.get('ai_summary')}")
        if res.get("red_flags"):
            print(f"  • ⚠️ Предупреждения: {res.get('red_flags')}")
    print("\n" + "=" * 60)


def run_demo(analyzer, notifier):
    """Simulates an entire scanning and notification flow without external services."""
    print("\n" + "=" * 60)
    print("ДЕМОНСТРАЦИЯ ПОЛНОГО ПАЙПЛАЙНА БОТА (БЕЗ ТЕЛЕГРАМА)")
    print("Имитация обнаружения новых объявлений и их оценки ИИ")
    print("=" * 60)

    sample_feed = [
        {
            "item_id": "demo_1001",
            "title": "Kingston Fury Beast Black DDR4 16GB (2x8GB) 3200MHz",
            "price": 1900,
            "raw_description": "Продам комплект памяти, полностью исправна, тесты MemTest без ошибок.",
            "location": "Москва",
            "url": "https://www.avito.ru/moskva/tovary_dlya_kompyutera/operativnaya_pamyat_demo1"
        },
        {
            "item_id": "demo_1002",
            "title": "Оперативная память Samsung 32Gb DDR4 ECC REG для сервера",
            "price": 1800,
            "raw_description": "Серверная память для двухпроцессорных плат x99 LGA2011-3.",
            "location": "Новосибирск",
            "url": "https://www.avito.ru/novosibirsk/tovary_dlya_kompyutera/operativnaya_pamyat_demo2"
        },
        {
            "item_id": "demo_1003",
            "title": "G.Skill Trident Z5 RGB DDR5 32GB (2x16GB) 6000MHz",
            "price": 5500,
            "raw_description": "Почти новая, покупалась 2 месяца назад, чек и коробка есть.",
            "location": "Санкт-Петербург",
            "url": "https://www.avito.ru/spb/tovary_dlya_kompyutera/operativnaya_pamyat_demo3"
        },
        {
            "item_id": "demo_1004",
            "title": "Corsair Vengeance DDR4 32Gb комплект 2x16",
            "price": 2400,
            "raw_description": "Цена указана за одну планку 16гб! В наличии 2 штуки.",
            "location": "Казань",
            "url": "https://www.avito.ru/kazan/tovary_dlya_kompyutera/operativnaya_pamyat_demo4"
        }
    ]

    for item in sample_feed:
        print(f"\n[Обработка] Найдено объявление: '{item['title']}' — {item['price']} ₽")
        analysis = analyzer.analyze(item["title"], item["price"], item["raw_description"], item["location"])
        item.update(analysis)

        if item.get("is_deal"):
            print(">>> 🔥 ИИ ОПРЕДЕЛИЛ СДЕЛКУ КАК ВЫГОДНУЮ! Формируем карточку...")
            notifier.send_deal_alert(item)
            item["notified"] = 1
        else:
            print(f">>> ❌ Пропущено: {item.get('ai_summary')}")
            item["notified"] = 0
            
        save_listing(item)

    print("\n" + "=" * 60)
    print("ДЕМОНСТРАЦИОННЫЙ ПРОГОН ЗАВЕРШЕН")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Avito RAM AI Sniper Bot")
    parser.add_argument("--scan", action="store_true", help="Выполнить один цикл сканирования")
    parser.add_argument("--loop", action="store_true", help="Запустить постоянный мониторинг")
    parser.add_argument("--setup", action="store_true", help="Открыть окно браузера для прохождения капчи")
    parser.add_argument("--test-ai", action="store_true", help="Протестировать анализ ИИ на тестовых объявлениях")
    parser.add_argument("--test-notify", action="store_true", help="Отправить тестовое уведомление в Telegram")
    parser.add_argument("--demo", action="store_true", help="Полный демо-прогон пайплайна с выводом карточек в терминал")
    parser.add_argument("--stats", action="store_true", help="Показать статистику базы данных")
    
    args = parser.parse_args()
    
    # Initialize DB
    init_db()
    
    config = load_config()
    analyzer = AIAnalyzer(api_key=config.gemini_api_key)
    notifier = TelegramNotifier(bot_token=config.telegram_bot_token, chat_id=config.telegram_chat_id)
    scraper = AvitoScraper(config)

    if args.setup:
        asyncio.run(run_setup(config))
    elif args.test_ai:
        run_test_ai(analyzer)
    elif args.demo:
        run_demo(analyzer, notifier)
    elif args.test_notify:
        print("Отправка тестового уведомления...")
        ok = notifier.test_connection()
        if ok:
            print("Уведомление успешно доставлено!")
        else:
            print("Ошибка отправки. Проверьте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в файле .env.")
    elif args.stats:
        stats = get_stats()
        print("\nСтатистика базы данных Avito AI Sniper:")
        print(f"  • Всего проанализировано объявлений: {stats['total_seen']}")
        print(f"  • Найдено выгодных сделок:           {stats['total_deals']}")
        print(f"  • Отправлено уведомлений:            {stats['total_notified']}\n")
    elif args.loop:
        asyncio.run(run_loop(config, scraper, analyzer, notifier))
    else:
        # Default: single scan
        asyncio.run(run_single_scan(config, scraper, analyzer, notifier))


if __name__ == "__main__":
    main()
