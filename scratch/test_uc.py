import undetected_chromedriver as uc
import time

def test_uc():
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = uc.Chrome(options=options)
    try:
        url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
        print(f"Navigating to {url}...")
        driver.get(url)
        time.sleep(5)
        print("Page title:", driver.title)
        
        # Check items
        items = driver.find_elements("css selector", '[data-marker="item"]')
        print(f"Items found: {len(items)}")
        if items:
            t = items[0].find_element("css selector", '[data-marker="item-title"]').text
            p = items[0].find_element("css selector", '[data-marker="item-price"]').text
            print(f"First item: {t} | {p}")
        else:
            print("Snippet:", driver.page_source[:500])
    finally:
        driver.quit()

if __name__ == "__main__":
    test_uc()
