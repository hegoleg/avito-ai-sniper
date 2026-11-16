import asyncio
from playwright.async_api import async_playwright

async def test_real():
    user_data_dir = "C:/Users/Egor/avito-ai-sniper/chrome_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            locale="ru-RU"
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Remove webdriver flag
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        print(f"Navigating to {url}...")
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        print("Response status:", resp.status if resp else "None")
        print("Title:", await page.title())
        await page.wait_for_timeout(4000)
        items = await page.query_selector_all('[data-marker="item"]')
        print("Items found:", len(items))
        if items:
            t = await items[0].query_selector('[data-marker="item-title"]')
            print("First item text:", await t.inner_text() if t else "No title text")
        else:
            print("Snippet:", (await page.content())[:600])
        await context.close()

if __name__ == "__main__":
    asyncio.run(test_real())
