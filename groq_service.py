from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
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
    async def validate_ingredients(text: str) -> bool:
        """Модерация ввода: только продукты."""
        prompt = (
            "You are a food safety moderator. Return ONLY JSON: {\"valid\": true} if input is food, "
            "otherwise {\"valid\": false}. Ignore language."
        )
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        return "true" in res.lower()

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        """Определяет категории блюд на основе продуктов."""
        prompt = (
            "Analyze ingredients and return ONLY a JSON array of keys: "
            "['soup', 'main', 'salad', 'breakfast', 'dessert', 'drink', 'snack']."
        )
        res = await GroqService._send_groq_request(prompt, products, 0.2)
        try:
            clean_json = re.search(r'\[.*\]', res, re.DOTALL).group()
            return json.loads(clean_json)
        except:
            return ["main"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str, style: str = "обычный", lang_code: str = "ru") -> List[Dict[str, str]]:
        is_ru = lang_code[:2].lower() == "ru"
        target_lang = "Russian" if is_ru else "the user's interface language"

        system_prompt = (
            f"You are a creative chef. Suggest 4-6 dishes. "
            f"STRICT LANGUAGE RULES:\n"
            f"1. Field 'name': Use the NATIVE language of the input ingredients (e.g., 'Tortilla de Patatas').\n"
            f"2. Field 'desc': Write the description strictly in {target_lang}.\n"
            f"3. Field 'display_name': If the user language is Russian and input is foreign, format as: 'Original Name (Russian Translation)'.\n"
            f"Return ONLY JSON list: [{{'name': '...', 'display_name': '...', 'desc': '...'}}]."
        )
        res = await GroqService._send_groq_request(system_prompt, f"Ingredients: {products}, Category: {category}, Style: {style}", 0.6)
        try:
            clean_json = re.search(r'\[.*\]', res, re.DOTALL).group()
            return json.loads(clean_json)
        except:
            return []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, lang_code: str = "ru") -> str:
        """Генерация экспертного рецепта с адаптивными единицами измерения и оригинальным названием."""
        languages = {"ru": "Russian", "en": "English", "es": "Spanish", "fr": "French", "de": "German"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")

        system_prompt = (
            f"You are a professional chef. Write a detailed recipe strictly in {target_lang}.\n\n"
            f"STRICT RULES:\n"
            f"1. NAME: Always use the ORIGINAL native name of the dish (e.g., 'Pasta Carbonara', 'Tortilla de Patatas') regardless of localization.\n"
            f"2. SILENT EXCLUSION: Do not mention ingredients that are NOT used.\n"
            f"3. INGREDIENT UNITS: Use realistic kitchen measurements. Most items in grams, BUT:\n"
            f"   - Oils/liquids: tablespoons (ст. л.) or teaspoons (ч. л.).\n"
            f"   - Garlic: cloves (зубчика).\n"
            f"   - Vegetables (carrots, beets, onions, etc.): pieces (шт.).\n"
            f"   - Format each line exactly as: '- ingredient - amount'.\n"
            f"4. KBHU: You MUST calculate numerical values per serving. Display nutritional information in the EXACT format:\n"
            f"   Энергетическая ценность: X ккал\n"
            f"   Белки: X г\n"
            f"   Жиры: X г\n"
            f"   Углеводы: X г\n"
            f"5. LOCALIZATION: Steps and labels MUST be in {target_lang}.\n"
            f"6. NO EMOJIS inside ingredient list or steps. No formatting like '**' in steps.\n"
            f"7. CULINARY TRIAD: Add 'Chef's Advice' (Taste, Aroma, Texture). Recommend EXACTLY ONE missing item.\n\n"
            f"STRUCTURE IN {target_lang.upper()}:\n"
            "🥘 [Original Native Name]\n\n"
            "📦 Ингредиенты:\n[List formatted as '- item - amount']\n\n"
            "Энергетическая ценность: X ккал\n"
            "Белки: X г\n"
            "Жиры: X г\n"
            "Углеводы: X г\n\n"
            "⏱ Время | 📈 Сложность | 👥 Порции\n\n"
            "🔪 Приготовление:\n[Steps without formatting]\n\n"
            "💡 Совет шеф-повара:\n[Triad Analysis]"
        )

        res = await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Ingredients: {products}", 0.3)
        
        farewell = {"ru": "Приятного аппетита!", "en": "Bon appétit!", "es": "¡Buen provecho!"}
        bon = farewell.get(lang_code[:2].lower(), "Приятного аппетита!")

        if GroqService._is_refusal(res): return res
        return f"{res}\n\n👨‍🍳 <b>{bon}</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str, lang_code: str = "ru") -> str:
        languages = {"ru": "Russian", "en": "English", "es": "Spanish"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")
        prompt = f"Write in {target_lang}. If food -> recipe. If abstraction -> metaphorical recipe. Safety: return '⛔ Извините, я готовлю только еду' if unsafe."
        res = await GroqService._send_groq_request(prompt, dish_name, 0.7)
        return res

    @staticmethod
    def _is_refusal(text: str) -> bool:
        refusals = ["cannot fulfill", "against my policy", "не могу ответить", "извините", "⛔"]
        return any(ph in text.lower() for ph in refusals)