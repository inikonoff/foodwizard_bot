from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL
from typing import Dict, List, Union
import json
import re
import logging

client = AsyncGroq(api_key=GROQ_API_KEY)
logger = logging.getLogger(__name__)

class GroqService:
    
    @staticmethod
    async def _send_groq_request(system_prompt: str, user_text: str, temperature: float = 0.5, max_tokens: int = 1500) -> str:
        try:
            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API Error: {e}")
            return ""

    @staticmethod
    def _extract_json(text: str) -> Union[Dict, List, None]:
        if not text:
            return None
        try:
            match = re.search(r'(?s)(\{.*\}|\[.*\])', text)
            if match:
                return json.loads(match.group())
        except:
            return None
        return None

    @staticmethod
    async def determine_intent(text: str) -> Dict[str, str]:
        prompt = (
            "Analyze input. Return ONLY JSON: "
            "{\"intent\": \"ingredients\"} or {\"intent\": \"recipe\", \"dish\": \"name\"}."
        )
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        if not data or "intent" not in data:
            return {"intent": "ingredients"}
        return data

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        prompt = "Return ONLY JSON: {\"valid\": true} if input is food ingredients, else {\"valid\": false}."
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        return data.get("valid", True) if data else True

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        """Определяет категории с усиленной логикой для супов."""
        prompt = f"""Analyze these ingredients: {products}.
        
        STRICT RULES:
        1. If ingredients include (onion AND carrot AND water/meat/fish) -> ALWAYS include 'soup'.
        2. Return ONLY a JSON array of keys: ['soup', 'main', 'salad', 'breakfast', 'dessert', 'drink', 'snack'].
        3. Pick up to 3 most relevant categories."""
        
        res = await GroqService._send_groq_request(prompt, "", 0.2)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else ["main", "snack"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str, lang_code: str = "ru") -> List[Dict[str, str]]:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")
        
        system_prompt = f"""You are a creative chef. Suggest 4-6 dishes in category '{category}'.
        STRICT LANGUAGE RULES:
        1. Field 'name': Use the NATIVE language of the dish (e.g., 'Insalata Estiva' or 'Pollo alla Cacciatora'). This is for buttons.
        2. Field 'desc': Write the description strictly in {target_lang}.
        3. Field 'display_name': If input is not in {target_lang}, format as: 'Original Name ({target_lang} Translation)'.
        4. Always assume basics (water, salt, oil, sugar, pepper, ice) are available.
        5. If the ingredients allow for making a liquid dish (soup/broth) using water, carrots and onion ALWAYS include 'soup' in the list.
        Return ONLY JSON: [{{"name": "...", "display_name": "...", "desc": "..."}}]."""
        
        res = await GroqService._send_groq_request(system_prompt, f"Ingredients: {products}", 0.6)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, lang_code: str = "ru") -> str:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish", "fr": "French"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")

        system_prompt = f"""You are a professional chef. Write a recipe strictly in {target_lang}.
        
        STRICT VISUAL RULES:
        1. TITLE: Use the ORIGINAL native name (e.g., 'Poulet à la Fricassée').
        2. BILINGUAL INGREDIENTS:
           - Detect the language of each input ingredient.
           - If it's NOT in {target_lang}, format as: '- Original (Translation) - amount'.
           - Example: '- Pollo (Курица) - 1 кг'.
        3. NUTRITION: Calculate per serving with emojis: 📊, 🥚, 🥑, 🌾, ⚡.
        4. CULINARY TRIAD: End with '💡 Совет шеф-повара (Кулинарная триада)'. 
           Analyze Taste, Aroma, and Texture. Recommend one missing item for balance.
        5. NO BOLD text in steps.
        
        STRUCTURE:
        🥘 [Original Name]
        
        📦 ИНГРЕДИЕНТЫ:
        [Bilingual list]
        
        📊 Пищевая ценность...
        ⏱ Время | 🎚 Сложность | 👥 Порции
        
        🔪 Приготовление:
        [Steps]
        
        💡 Совет шеф-повара (Кулинарная триада):
        [Analysis]"""

        res = await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Products: {products}", 0.3)
        
        farewells = {"ru": "Приятного аппетита!", "en": "Bon appétit!", "es": "¡Buen provecho!"}
        bon = farewells.get(lang_code[:2].lower(), "Приятного аппетита!")
        
        return f"{res}\n\n👨‍🍳 <b>{bon}</b>"