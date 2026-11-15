import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def test_fetch():
    url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
    print(f"Connecting to: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="ru-RU"
        )
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print(f"Status code: {response.status if response else 'None'}")
            print(f"Page title: {await page.title()}")
            
            # Check for items
            await page.wait_for_timeout(3000)
            items = await page.query_selector_all('[data-marker="item"]')
            print(f"Found items: {len(items)}")
            
            if items:
                first = items[0]
                title_elem = await first.query_selector('[data-marker="item-title"]')
                title = await title_elem.inner_text() if title_elem else "No title"
                
                price_elem = await first.query_selector('[data-marker="item-price"]')
                price = await price_elem.inner_text() if price_elem else "No price"
                
                link_elem = await first.query_selector('a[data-marker="item-title"]')
                href = await link_elem.get_attribute("href") if link_elem else "No link"
                
                print(f"First item sample: Title='{title}', Price='{price}', Link='{href}'")
            else:
                content = await page.content()
                print(f"Page snippet: {content[:1000]}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_fetch())
