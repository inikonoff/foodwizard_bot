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
        """
        Генерирует список названий блюд на нативном языке (для кнопок), 
        но описание и отображение (display_name) на языке локализации.
        """
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
        """Генерация экспертного рецепта с обязательным расчетом КБЖУ."""
        languages = {"ru": "Russian", "en": "English", "es": "Spanish", "fr": "French", "de": "German"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")

        system_prompt = (
            f"You are a professional chef. Write a detailed recipe strictly in {target_lang}.\n\n"
            f"STRICT RULES:\n"
            f"1. SILENT EXCLUSION: Do not mention or list any provided ingredients that are NOT used in this recipe.\n"
            f"2. INGREDIENT LIST FORMAT: Format each line exactly as: '- ingredient - amount'. Example: '- картофель - 300 г'.\n"
            f"3. KBHU CALCULATION: You MUST calculate and provide specific numerical values for Calories, Proteins, Fats, and Carbs PER SERVING based on the ingredients used. FORMAT: each line exactly as: 'Calories - amount' etc.Do not use vague phrases like 'to be clarified'. Provide estimated digits in a separate line (e.g., 'Энергеттческая ценность: 450 ккал, Белки: 20г, Жиры: 15г, Углеводы: 40г').\n"
            f"4. LOCALIZATION: All parts (Title, Labels, Ingredients, Steps) MUST be in {target_lang}.\n"
            f"5. SMART SUBSTITUTES: Use logical substitutes from the user list if needed.\n"
            f"6. NO EMOJIS inside ingredient list or steps. No checkmarks. No formatting like '**' in steps.\n"
            f"7. CULINARY TRIAD: Add 'Chef's Advice' section analyzing Taste, Aroma, Texture. Recommend EXACTLY ONE missing item to finish the triad.\n\n"
            f"STRUCTURE IN {target_lang.upper()}:\n"
            "🥘 [Original Dish Name]\n\n"
            "📦 Ингредиенты:\n[List formatted as '- item - amount']\n\n"
            "📊 КБЖУ на порцию:\n[Numerical data only, e.g., Калории: X ккал, Б: X г, Ж: X г, У: X г]\n\n"
            "⏱ Время \n 📈 Сложность \n 👥 Порции\n\n"
            "🔪 Приготовление:\n[Steps without formatting]\n\n"
            "💡 Совет шеф-повара:\n[Triad Analysis]"
        )

        res = await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Ingredients: {products}", 0.3)
        
        farewell = {"ru": "Приятного аппетита!", "en": "Bon appétit!", "es": "¡Buen provecho!", "fr": "Bon appétit!"}
        bon = farewell.get(lang_code[:2].lower(), "Приятного аппетита!")

        if GroqService._is_refusal(res): return res
        return f"{res}\n\n👨‍🍳 <b>{bon}</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str, lang_code: str = "ru") -> str:
        """Свободные/метафорические рецепты."""
        languages = {"ru": "Russian", "en": "English", "es": "Spanish"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")
        
        prompt = (
            f"Write in {target_lang}. Food -> Recipe. Abstraction -> Metaphorical recipe. "
            "Safety: If dangerous/prohibited, return ONLY: '⛔ Извините, я готовлю только еду.'"
        )
        res = await GroqService._send_groq_request(prompt, dish_name, 0.7)
        return res

    @staticmethod
    def _is_refusal(text: str) -> bool:
        refusals = ["cannot fulfill", "against my policy", "не могу ответить", "извините", "⛔"]
        return any(ph in text.lower() for ph in refusals)