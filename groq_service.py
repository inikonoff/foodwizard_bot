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
        """Метод с логикой повторных попыток (Retry Logic)."""
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
                if res_content:
                    return res_content
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
            if match:
                return json.loads(match.group())
        except Exception:
            return None
        return None

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        system_prompt = """Analyze ingredients. Return ONLY a JSON array of keys from: 
        ['soup', 'main', 'salad', 'breakfast', 'dessert', 'drink', 'snack'].
        
        STRICT RULES:
        1. Base: (water + salt + onion + carrot) = MUST suggest 'soup'.
        2. Liquid base: (fruit/vegetable + milk/water) = MUST suggest 'drink' (smoothie/cocktail).
        3. Max 4 most relevant categories."""
        
        res = await GroqService._send_groq_request(system_prompt, products, temperature=0.2)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else ["main", "snack"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str, lang_code: str = "ru") -> List[Dict[str, str]]:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")
        
        system_prompt = f"""Suggest 4-6 dishes in category '{category}'.
        
        STRICT FORMATTING:
        1. 'name': Use ONLY the original native name.
        2. 'display_name': Use ONLY the original native name. NO brackets, NO translations.
        3. 'desc': Write a short tasty description STRICTLY in {target_lang}.
        4. No transliterations.
        
        Return ONLY JSON: [{{"name": "...", "display_name": "...", "desc": "..."}}]."""
        
        res = await GroqService._send_groq_request(system_prompt, f"Ingredients: {products}", temperature=0.6)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, lang_code: str = "ru") -> str:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")

        system_prompt = f"""Write a recipe for '{dish_name}' in {target_lang}.
        
        STRICT RULES:
        1. HEADER: Always use the original native name. Never translate it.
        2. SILENT EXCLUSION: Use only provided products + basics (water, salt, pepper, oil, sugar).
        3. INGREDIENTS: 
           - If input was foreign, format: '- Original (Translation to {target_lang}) - amount'.
           - If input was in {target_lang}, just: '- Name - amount'.
        4. NUTRITION & INFO: Each parameter MUST be on a NEW LINE.
        5. CULINARY TRIAD: End with advice in {target_lang} (Taste, Aroma, Texture).

        STRUCTURE:
        🥘 [Original Name ONLY]
        
        📦 ИНГРЕДИЕНТЫ:
        [List]
        
        ⏱ Время: XX мин
        🎚 Сложность: XX
        👥 Порции: XX
        
        📊 Пищевая ценность на 1 порцию:
        🥚 Белки: X г
        🥑 Жиры: X г
        🌾 Углеводы: X г
        ⚡ Энерг. ценность: X ккал

        🔪 Приготовление:
        [Steps - No bold]

        💡 Совет шеф-повара (Кулинарная триада):
        [Analysis in {target_lang}]"""

        res = await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Products: {products}", temperature=0.4)
        
        farewells = {"ru": "Приятного аппетита!", "en": "Bon appétit!", "es": "¡Buen provecho!"}
        bon = farewells.get(lang_code[:2].lower(), "Приятного аппетита!")
        return f"{res}\n\n👨‍🍳 <b>{bon}</b>"

    @staticmethod
    def get_welcome_message() -> str:
        return """👋 Здравствуйте.
🎤 Отправьте голосовое или текстовое сообщение с перечнем продуктов, и я подскажу, что из них можно приготовить.
📝 Или напишите "Дай рецепт [блюдо]"."""