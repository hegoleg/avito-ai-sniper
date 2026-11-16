import asyncio
import re
import urllib.request
import cv2
import numpy as np
import random
from playwright.async_api import async_playwright

def find_geetest_gap(bg_bytes, slice_y=54):
    nparr = np.frombuffer(bg_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w, _ = img.shape
    
    # We know the slice is roughly at slice_y (e.g. 40 to 120)
    # The gap is a darkened silhouette
    # Let's crop region of interest around Y
    y1 = max(0, int(slice_y - 10))
    y2 = min(h, int(slice_y + 80))
    
    roi = img[y1:y2, 70:w] # gap is always past x=70
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Gap is typically much darker than surroundings
    # Find minimum brightness column or edge profile
    col_mean = np.mean(gray_roi, axis=0)
    # Smooth
    kernel = np.ones(15) / 15
    smoothed = np.convolve(col_mean, kernel, mode='same')
    
    # Find trough
    min_x = np.argmin(smoothed[10:-10]) + 10 + 70
    return min_x

async def human_drag(page, start_x, start_y, distance):
    # Mouse move to start
    await page.mouse.move(start_x, start_y)
    await page.wait_for_timeout(random.randint(150, 300))
    await page.mouse.down()
    await page.wait_for_timeout(random.randint(80, 150))
    
    current_x = start_x
    current_y = start_y
    steps = random.randint(25, 35)
    
    # Human-like curve: fast start, slow near end with slight overshoot/back
    for i in range(steps):
        t = (i + 1) / steps
        # easeOutQuad curve
        progress = 1 - (1 - t) * (1 - t)
        target_step_x = start_x + (distance * progress)
        dx = target_step_x - current_x
        dy = random.uniform(-1.5, 1.5)
        
        current_x += dx
        current_y += dy
        await page.mouse.move(current_x, current_y)
        await page.wait_for_timeout(random.randint(10, 25))
        
    await page.wait_for_timeout(random.randint(100, 250))
    await page.mouse.up()
    await page.wait_for_timeout(1000)

async def test_solve():
    profile_dir = "C:/Users/Egor/avito-ai-sniper/profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(profile_dir, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()
        url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        await page.goto(url)
        await page.wait_for_timeout(2000)
        
        btn = await page.query_selector('button')
        if not btn:
            print("No challenge button found, page might already be unlocked!")
            print("Title:", await page.title())
            await context.close()
            return
            
        await btn.click()
        await page.wait_for_timeout(3000)
        
        # Get GeeTest elements
        info = await page.evaluate('''() => {
            const bg = document.querySelector('[class*="geetest_bg"]');
            const btn = document.querySelector('[class*="geetest_btn"]');
            const slice = document.querySelector('[class*="geetest_slice"]');
            if (!bg || !btn) return null;
            return {
                bgUrl: bg.style.backgroundImage,
                bgBox: bg.getBoundingClientRect(),
                btnBox: btn.getBoundingClientRect(),
                sliceBox: slice ? slice.getBoundingClientRect() : null,
            };
        }''')
        
        if not info:
            print("Could not find GeeTest elements")
            await context.close()
            return
            
        m = re.search(r'url\(["\']?(.*?)["\']?\)', info['bgUrl'])
        bg_url = m.group(1) if m else None
        print(f"Background URL: {bg_url}")
        
        if bg_url:
            req = urllib.request.Request(bg_url, headers={'User-Agent': 'Mozilla/5.0'})
            bg_data = urllib.request.urlopen(req).read()
            slice_y = (info['sliceBox']['top'] - info['bgBox']['top']) if info['sliceBox'] else 54
            gap_x = find_geetest_gap(bg_data, slice_y)
            print(f"Detected gap X at: {gap_x}")
            
            # Button coords
            btn_box = info['btnBox']
            start_x = btn_box['x'] + btn_box['width'] / 2
            start_y = btn_box['y'] + btn_box['height'] / 2
            
            # The distance to drag button is proportional to gap_x
            # Width of bg is 300, bounding client rect width is ~301
            drag_distance = gap_x * (info['bgBox']['width'] / 300.0)
            print(f"Dragging button from ({start_x}, {start_y}) by {drag_distance} px...")
            
            await human_drag(page, start_x, start_y, drag_distance)
            await page.wait_for_timeout(3000)
            
            title_after = await page.title()
            print("Title after drag:", title_after)
            await page.screenshot(path="C:/Users/Egor/avito-ai-sniper/after_drag.png")
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(test_solve())
