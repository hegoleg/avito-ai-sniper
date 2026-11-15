import asyncio
from playwright.async_api import async_playwright

async def interactive_test():
    profile_dir = "C:/Users/Egor/avito-ram-sniper/profile"
    print("Launching visible browser with persistent context...")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            viewport={"width": 1280, "height": 850},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        print(f"Opening {url}...")
        await page.goto(url)
        
        print("Waiting 15 seconds to observe behavior...")
        for i in range(15):
            await page.wait_for_timeout(1000)
            title = await page.title()
            print(f"[{i+1}s] Title: {title}")
            items = await page.query_selector_all('[data-marker="item"]')
            if len(items) > 0:
                print(f"SUCCESS! Found {len(items)} items!")
                break
                
        await context.close()

if __name__ == "__main__":
    asyncio.run(interactive_test())
