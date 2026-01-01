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
        1. Field 'name': Use the NATIVE language of the dish (e.g., 'Gazpacho'). This is the ID.
        2. Field 'display_name': Use ONLY the format 'Native Name (Translation to {target_lang})'. Example: 'Gazpacho (Гаспачо)'.
        3. Field 'desc': Write a short description strictly in {target_lang}.
        4. Field 'original_name': The name in its native language.
        Return ONLY JSON: [{{"name": "...", "display_name": "...", "desc": "...", "original_name": "..."}}]."""
        
        res = await GroqService._send_groq_request(system_prompt, f"Ingredients: {products}", 0.6)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, lang_code: str = "ru") -> str:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish", "fr": "French"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")

        system_prompt = f"""You are a professional chef. Write a recipe strictly in {target_lang}.
        
        STRICT VISUAL RULES:
        1. TITLE: Use ONLY the ORIGINAL native name of the dish as provided. Do NOT translate it.
        2. INGREDIENTS:
           - Detect the language of input ingredients.
           - If NOT in {target_lang}, format: '- Original (Translation) - amount'.
           - If in {target_lang}, format: '- Original - amount'.
        3. STRUCTURE (MANDATORY ORDER):
           🥘 [Original Name ONLY]
           
           📦 ИНГРЕДИЕНТЫ:
           [List]
           
           ⏱ Время | 🎚 Сложность | 👥 Порции
           
           📊 Пищевая ценность на 1 порцию:
              🥚 Белки: X г
              🥑 Жиры: X г
              🌾 Углеводы: X г
              ⚡ Энерг. ценность: X ккал

           🔪 Приготовление:
           [Steps - NO BOLD]
           
           💡 Совет шеф-повара (Кулинарная триада):
           [Analysis in {target_lang} summarizing Taste, Aroma, and Texture]"""

        res = await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Products: {products}", 0.3)
        farewells = {"ru": "Приятного аппетита!", "en": "Bon appétit!", "es": "¡Buen provecho!"}
        bon = farewells.get(lang_code[:2].lower(), "Приятного аппетита!")
        
        return f"{res}\n\n👨‍🍳 <b>{bon}</b>"

    @staticmethod
    def get_welcome_message() -> str:
        return """👋 Здравствуйте.

🎤 Отправьте голосовое или текстовое сообщение с перечнем продуктов, и я подскажу, что из них можно приготовить.
📝 Или напишите "Дай рецепт [блюдо]"."""