import asyncio
from playwright.async_api import async_playwright

async def dump_439():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        resp = await page.goto('https://www.avito.ru')
        content = await page.content()
        with open('avito_439.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Saved avito_439.html, length:', len(content))
        await browser.close()

asyncio.run(dump_439())
