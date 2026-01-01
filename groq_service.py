from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL
from typing import Dict, List, Union, Optional
import json
import re
import logging
import asyncio

client = AsyncGroq(api_key=GROQ_API_KEY)
logger = logging.getLogger(__name__)

class GroqService:
    
    @staticmethod
    async def _send_groq_request(system_prompt: str, user_text: str, temperature: float = 0.5, max_tokens: int = 1500, retries: int = 1) -> str:
        current_temp = temperature
        for attempt in range(retries + 1):
            try:
                response = await client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text}
                    ],
                    max_tokens=max_tokens,
                    temperature=current_temp
                )
                res_content = response.choices[0].message.content.strip()
                if res_content: return res_content
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
            
            current_temp = 0.0
            await asyncio.sleep(1) 
        return ""

    @staticmethod
    def _extract_json(text: str) -> Union[Dict, List, None]:
        if not text: return None
        try:
            match = re.search(r'(?s)(\{.*\}|\[.*\])', text)
            if match: return json.loads(match.group())
        except Exception: return None
        return None

    @staticmethod
    async def determine_intent(text: str) -> Dict[str, str]:
        prompt = "Analyze input. Return ONLY JSON: {\"intent\": \"ingredients\"} or {\"intent\": \"recipe\", \"dish\": \"name\"}."
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        return data if data else {"intent": "ingredients"}

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        prompt = "Return ONLY JSON: {\"valid\": true} if input is food, else {\"valid\": false}."
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        return data.get("valid", True) if data else True

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        system_prompt = """Return ONLY a JSON array of keys: ['soup', 'main', 'salad', 'breakfast', 'dessert', 'drink', 'snack'].
        Rules: water+salt+onion+carrot = 'soup'. fruit+milk/water = 'drink'."""
        res = await GroqService._send_groq_request(system_prompt, products, 0.2)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else ["main"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str, lang_code: str = "ru") -> List[Dict[str, str]]:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")
        
        system_prompt = f"""Suggest 4-6 dishes in category '{category}'.
        
        STRICT RULES:
        1. 'display_name': ONLY the original name. NO BRACKETS. NO TRANSLATIONS. 
           Example: 'Soffritto di Verdure' (Correct), 'Soffritto di Verdure (Обжарка)' (WRONG).
        2. 'desc': Short description strictly in {target_lang}.
        
        Return ONLY JSON: [{{"name": "...", "display_name": "...", "desc": "..."}}]."""
        
        res = await GroqService._send_groq_request(system_prompt, f"Ingredients: {products}", 0.6)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, lang_code: str = "ru") -> str:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")

        system_prompt = f"""Write a recipe for '{dish_name}' in {target_lang}.
        
        STRICT RULES:
        1. TITLE: Use ONLY the original name provided. NO TRANSLATIONS in the title.
        2. INGREDIENTS: Use only provided items + basics. Format: '- Name - amount'.
        3. FORMATTING: Nutrition, Time, Difficulty, Servings - EACH ON A NEW LINE.
        
        STRUCTURE:
        🥘 [Original Name]
        
        📦 ИНГРЕДИЕНТЫ:
        [List]
        
        ⏱ Время: XX
        🎚 Сложность: XX
        👥 Порции: XX
        
        📊 Пищевая ценность на 1 порцию:
        🥚 Белки: X г
        🥑 Жиры: X г
        🌾 Углеводы: X г
        ⚡ Энерг. ценность: X ккал

        🔪 Приготовление:
        [Steps]

        💡 Совет шеф-повара:
        [Advice in {target_lang}]"""

        return await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Products: {products}", 0.3)

    @staticmethod
    def get_welcome_message() -> str:
        return "👋 Я ваш ИИ-шеф. Пришлите список продуктов или название блюда."