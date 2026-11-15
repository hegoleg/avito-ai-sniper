import asyncio
from playwright.async_api import async_playwright

async def get_title():
    profile_dir = "C:/Users/Egor/avito-ram-sniper/profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            profile_dir,
            headless=True
        )
        page = context.pages[0] if context.pages else await context.new_page()
        url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        await page.goto(url)
        await page.wait_for_timeout(4000)
        title = await page.title()
        url_now = page.url
        with open("C:/Users/Egor/avito-ram-sniper/page_title.txt", "w", encoding="utf-8") as f:
            f.write(f"Title: {title}\nURL: {url_now}\n")
        await context.close()

if __name__ == "__main__":
    asyncio.run(get_title())
