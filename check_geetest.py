import asyncio
from playwright.async_api import async_playwright

async def check():
    profile_dir = "C:/Users/Egor/avito-ram-sniper/profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(profile_dir, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104")
        await page.wait_for_timeout(2000)
        btn = await page.query_selector('button')
        if btn:
            await btn.click()
            await page.wait_for_timeout(2500)
            
            canvases = await page.query_selector_all('canvas')
            print("Canvas count:", len(canvases))
            for i, c in enumerate(canvases):
                box = await c.bounding_box()
                cls = await c.get_attribute("class")
                print(f"Canvas {i}: class={cls}, box={box}")
                
            slider_btn = await page.query_selector('[class*="geetest_btn"]')
            if slider_btn:
                print("Slider btn box:", await slider_btn.bounding_box())
        await context.close()

if __name__ == "__main__":
    asyncio.run(check())
