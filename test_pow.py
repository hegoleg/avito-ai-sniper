import asyncio
from playwright.async_api import async_playwright

async def test_pow():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            locale="ru-RU"
        )
        page = await context.new_page()
        
        url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        print(f"Navigating to {url}...")
        resp = await page.goto(url, timeout=30000)
        print("Initial Title:", await page.title())
        
        # Check if we got the firewall PoW challenge
        for i in range(15):
            title = await page.title()
            print(f"[{i}s] Current title: {title}")
            if "проверка безопасности" in title.lower() or "доступ ограничен" in title.lower():
                await page.wait_for_timeout(1000)
            else:
                print("Successfully bypassed challenge! Found page:", title)
                break
                
        # Wait for items to render
        await page.wait_for_timeout(3000)
        items = await page.query_selector_all('[data-marker="item"]')
        print(f"Total items found: {len(items)}")
        
        for item in items[:5]:
            t = await item.query_selector('[data-marker="item-title"]')
            p = await item.query_selector('[data-marker="item-price"]')
            link = await item.query_selector('a[data-marker="item-title"]')
            title_text = await t.inner_text() if t else "N/A"
            price_text = await p.inner_text() if p else "N/A"
            href = await link.get_attribute("href") if link else "N/A"
            print(f"- {title_text} | {price_text} | https://www.avito.ru{href}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_pow())
