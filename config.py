"""
Configuration module for Avito AI Monitor.
Loads settings from .env file and provides structured config objects.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_PATH)


@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    gemini_api_key: str
    
    # Search settings
    search_query: str
    search_location: str
    category_path: str
    min_price: int
    max_price: int
    
    # Polling & Scraper
    poll_interval_minutes: int
    headless: bool
    proxy_url: Optional[str]
    user_data_dir: str


def load_config() -> Config:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_dir = os.path.join(base_dir, "profile")
    
    return Config(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        
        search_query=os.getenv("SEARCH_QUERY", "").strip(),
        search_location=os.getenv("SEARCH_LOCATION", "all").strip(),
        category_path=os.getenv(
            "CATEGORY_PATH", 
            "all/tovary_dlya_kompyutera/komplektuyuschie/operativnaya_pamyat-ASgBAgICAkTGB~pm7gnYZw"
        ).strip(),
        min_price=int(os.getenv("MIN_PRICE", "500")),
        max_price=int(os.getenv("MAX_PRICE", "25000")),
        
        poll_interval_minutes=int(os.getenv("POLL_INTERVAL_MINUTES", "4")),
        headless=os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes"),
        proxy_url=os.getenv("PROXY_URL", "").strip() or None,
        user_data_dir=os.getenv("USER_DATA_DIR", profile_dir)
    )
