import asyncio
from playwright.async_api import async_playwright

async def inspect_dom():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            locale="ru-RU",
            viewport={"width": 1400, "height": 900}
        )
        page = await context.new_page()
        url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        await page.goto(url)
        
        # Wait until bypass
        for _ in range(10):
            title = await page.title()
            if "безопасности" not in title and "ограничен" not in title:
                break
            await page.wait_for_timeout(1000)
            
        print("Page title:", await page.title())
        await page.wait_for_timeout(3000)
        
        # Look for markers
        markers = await page.evaluate("""
            () => {
                const elements = Array.from(document.querySelectorAll('[data-marker]'));
                const markerNames = new Set(elements.map(el => el.getAttribute('data-marker')));
                return Array.from(markerNames).slice(0, 40);
            }
        """)
        print("Found data-markers:", markers)
        
        # Try item elements
        item_selectors = [
            '[data-marker="item"]',
            '[data-marker*="item"]',
            'div[class*="items-items"] > div',
            'div[class*="iva-item-root"]',
            'div[data-item-id]'
        ]
        for sel in item_selectors:
            found = await page.query_selector_all(sel)
            print(f"Selector '{sel}': {len(found)} matches")
            
        # Get snippet of page HTML
        html = await page.content()
        with open("C:/Users/Egor/avito-ram-sniper/page_dom.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("DOM dumped to page_dom.html, size:", len(html))
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_dom())
