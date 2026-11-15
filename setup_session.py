import asyncio
import os
import sys
from playwright.async_api import async_playwright

PROFILE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "profile"))

async def setup_session():
    print("=" * 60)
    print("ИНИЦИАЛИЗАЦИЯ СЕССИИ АВИТО")
    print("Сейчас откроется окно браузера.")
    print("Если появится капча-пазл (слайдер) — передвиньте его мышкой.")
    print("Как только страница Авито загрузится, сессия сохранится.")
    print("=" * 60)
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 850},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        target_url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        print(f"Переходим на {target_url}...")
        await page.goto(target_url)
        
        # Check if button "Продолжить" exists and click it to trigger captcha
        await page.wait_for_timeout(2000)
        btn = await page.query_selector('button:has-text("Продолжить"), .button-continue')
        if btn:
            print("Нажимаем кнопку 'Продолжить' для открытия капчи...")
            await btn.click()
            
        print("Ожидаем прохождения проверки (до 60 секунд)...")
        success = False
        for sec in range(60):
            await page.wait_for_timeout(1000)
            title = await page.title()
            items = await page.query_selector_all('[data-marker="item"]')
            
            if len(items) > 0 or ("оперативная память" in title.lower() and "проблема с ip" not in title.lower() and "безопасности" not in title.lower()):
                print(f"\n[УСПЕХ] Проверка пройдена! Заголовок: {title}")
                print(f"Найдено объявлений на странице: {len(items)}")
                success = True
                await page.wait_for_timeout(2000)
                break
            else:
                if (sec + 1) % 5 == 0:
                    print(f"Ждем решения капчи... ({sec + 1}/60 сек). Заголовок: {title}")
                    
        await context.close()
        
        if success:
            print("\nСессия успешно сохранена в папку профиля! Теперь бот может работать автономно.")
        else:
            print("\nКапча не была пройдена за отведенное время. Запустите скрипт снова при необходимости.")

if __name__ == "__main__":
    asyncio.run(setup_session())
