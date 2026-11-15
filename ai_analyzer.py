"""
AI Deal Analyzer module.
Uses Google Gemini Flash API with structured JSON output, with automatic
fallback to domain heuristic analysis if API key is not configured.
"""

import json
import logging
import os
import re
from typing import Dict, Any, Optional

from ram_knowledge import evaluate_deal_heuristic, BENCHMARKS

logger = logging.getLogger(__name__)

GEMINI_SYSTEM_PROMPT = """
Ты — профессиональный эксперт по компьютерному железу и оценщик объявлений на вторичном рынке (Авито).
Твоя задача — объективно оценить объявление о продаже оперативной памяти (ОЗУ / RAM).

Особое внимание обрати на подводные камни:
1. Серверная память (ECC REG, Registered, RDIMM, LRDIMM, для серверов, Huananzhi, X79, X99, Xeon) — она НЕ РАБОТАЕТ в обычных материнских платах для домашних ПК (Intel Core i3/i5/i7/i9, AMD Ryzen). Если это серверная память, сделка НЕ является выгодной для обычного пользователя (is_deal = false, red_flags = ["Серверная память ECC REG"]).
2. Ловушка с ценой: в заголовке указан комплект (например, 32GB 2x16), а в описании продавец пишет "цена за одну плашку" или "цена за 16гб".
3. Неисправности: "на запчасти", "не стартует", "синий экран (BSOD)", "после залития/грозы", "битая банка".
4. Память для ноутбуков (SO-DIMM): пометить form_factor = "LAPTOP_SODIMM".

Ориентировочные рыночные цены б/у (в рублях):
- DDR4 16GB (2x8GB комплект): рынок ~3000₽ (хорошая цена < 2400₽, суперцена < 1900₽)
- DDR4 32GB (2x16GB комплект): рынок ~6200₽ (хорошая цена < 4800₽, суперцена < 3900₽)
- DDR5 32GB (2x16GB комплект): рынок ~9800₽ (хорошая цена < 7600₽, суперцена < 6000₽)

Ты должен ответить ТОЛЬКО в формате JSON со следующими полями:
{
  "ram_type": "DDR4" | "DDR5" | "DDR3" | "Unknown",
  "capacity_gb": 16,
  "is_kit": true,
  "form_factor": "DESKTOP_DIMM" | "LAPTOP_SODIMM" | "SERVER_ECC",
  "frequency_mhz": 3200,
  "is_deal": true | false,
  "deal_rating": "TOP_DEAL" | "GOOD_DEAL" | "FAIR_PRICE" | "BAD_DEAL" | "SUSPICIOUS",
  "estimated_market_price": 3000,
  "red_flags": ["список предупреждений, если есть"],
  "ai_summary": "Краткое (1-2 предложения) понятное резюме на русском языке: почему это выгодно или почему не стоит брать"
}
"""


class AIAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Gemini AI Client initialized successfully.")
            except Exception as e:
                logger.warning("Failed to initialize google-genai client: %s. Using heuristic fallback.", e)
        else:
            logger.info("No GEMINI_API_KEY provided. Operating in rule-based heuristic mode.")

    def analyze(self, title: str, price: Optional[int], description: str = "", location: str = "") -> Dict[str, Any]:
        """Analyzes a listing using Gemini or falls back to heuristics."""
        if not self.client:
            return evaluate_deal_heuristic(title, price, description)
            
        try:
            prompt = f"""
Проанализируй объявление:
Заголовок: {title}
Цена: {price} руб.
Город/Локация: {location}
Описание продавца:
{description if description else "(описание не указано)"}
"""
            # Call Gemini 2.5 Flash / 2.0 Flash
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "system_instruction": GEMINI_SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                }
            )
            
            raw_text = response.text.strip()
            # Clean markdown codeblocks if any
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text)
                
            data = json.loads(raw_text)
            
            # Sanitize fields
            return {
                "ram_type": data.get("ram_type", "Unknown"),
                "capacity_gb": data.get("capacity_gb"),
                "is_kit": bool(data.get("is_kit", False)),
                "form_factor": data.get("form_factor", "DESKTOP_DIMM"),
                "frequency_mhz": data.get("frequency_mhz"),
                "is_deal": bool(data.get("is_deal", False)),
                "deal_rating": data.get("deal_rating", "FAIR_PRICE"),
                "estimated_market_price": data.get("estimated_market_price"),
                "red_flags": data.get("red_flags", []),
                "ai_summary": data.get("ai_summary", "")
            }
        except Exception as e:
            logger.warning("Gemini AI analysis error (%s). Falling back to heuristic rules.", e)
            return evaluate_deal_heuristic(title, price, description)
