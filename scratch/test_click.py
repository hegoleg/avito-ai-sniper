import asyncio
from playwright.async_api import async_playwright

async def click_continue():
    profile_dir = "C:/Users/Egor/avito-ai-sniper/profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(profile_dir, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104")
        await page.wait_for_timeout(3000)
        
        # Look for the button
        btn = await page.query_selector('button:has-text("Продолжить"), .button-continue, button')
        if btn:
            print("Found button:", await btn.inner_text())
            await btn.click()
            print("Clicked button! Waiting 4s...")
            await page.wait_for_timeout(4000)
            await page.screenshot(path="C:/Users/Egor/avito-ai-sniper/after_click.png")
            print("Title after click:", await page.title())
        else:
            print("No button found")
        await context.close()

if __name__ == "__main__":
    asyncio.run(click_continue())
