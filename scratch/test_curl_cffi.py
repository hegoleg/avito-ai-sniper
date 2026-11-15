from curl_cffi import requests
from bs4 import BeautifulSoup

def test():
    s = requests.Session(impersonate="chrome124")
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    url = "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTmAeKKAZb9Cg?s=104"
    r = s.get(url, headers=headers, timeout=15)
    print("Status code:", r.status_code)
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.string if soup.title else "No title"
    print("Page title:", title)
    
    items = soup.select('[data-marker="item"]')
    print("Found items via selector:", len(items))
    if items:
        first = items[0]
        title_tag = first.select_one('[data-marker="item-title"]')
        price_tag = first.select_one('[data-marker="item-price"]')
        link_tag = first.select_one('a[data-marker="item-title"]')
        print("First item:", {
            "title": title_tag.get_text(strip=True) if title_tag else None,
            "price": price_tag.get_text(strip=True) if price_tag else None,
            "href": link_tag.get("href") if link_tag else None
        })

if __name__ == "__main__":
    test()
