import asyncio
from playwright.async_api import async_playwright

async def inspect_images():
    profile_dir = "C:/Users/Egor/avito-ai-sniper/profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(profile_dir, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104")
        await page.wait_for_timeout(2000)
        btn = await page.query_selector('button')
        if btn:
            await btn.click()
            await page.wait_for_timeout(2500)
            
            info = await page.evaluate('''() => {
                const bg = document.querySelector('[class*="geetest_bg"]');
                const slice = document.querySelector('[class*="geetest_slice"]');
                return {
                    bgStyle: bg ? bg.style.backgroundImage : null,
                    bgBounding: bg ? bg.getBoundingClientRect() : null,
                    sliceStyle: slice ? slice.style.backgroundImage : null,
                    sliceBounding: slice ? slice.getBoundingClientRect() : null,
                };
            }''')
            print("GeeTest info:", info)
        await context.close()

if __name__ == "__main__":
    asyncio.run(inspect_images())
