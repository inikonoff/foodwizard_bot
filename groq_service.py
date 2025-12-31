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
    async def generate_dishes_list(products: str, category: str, style: str = "обычный") -> List[Dict[str, str]]:
        """Генерирует список блюд на языке ввода (для инлайн-кнопок)."""
        prompt = (
            f"Suggest 4-6 dishes in category '{category}' using provided ingredients. Style: {style}. "
            "IMPORTANT: Use the SAME language as the input ingredients for names and descriptions. "
            "Return ONLY JSON list: [{\"name\": \"Dish Name\", \"desc\": \"Short description\"}]."
        )
        res = await GroqService._send_groq_request(prompt, f"Ingredients: {products}", 0.6)
        try:
            clean_json = re.search(r'\[.*\]', res, re.DOTALL).group()
            return json.loads(clean_json)
        except:
            return []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, lang_code: str = "ru") -> str:
        """Генерация экспертного рецепта с локализацией всех сущностей."""
        languages = {"ru": "Russian", "en": "English", "es": "Spanish", "fr": "French", "de": "German"}
        target_lang = languages.get(lang_code[:2].lower(), "Russian")

        system_prompt = (
            f"You are a professional chef. Write a detailed recipe strictly in {target_lang}.\n\n"
            f"STRICT LOCALIZATION: All parts (Dish Name, Ingredients, KBHU labels, Steps, Tips) MUST be in {target_lang}.\n\n"
            "RULES:\n"
            "1. USE ONLY user products + BASIC items (water, salt, pepper, sugar, oil, flour, vinegar).\n"
            "2. SMART SUBSTITUTES: Use logical substitutes from user's list if needed (e.g. yogurt instead of sour cream).\n"
            "3. FORMATTING: Use emojis ONLY for headers. NO emojis or icons inside ingredients list (no checkmarks!) or steps.\n"
            "4. NO '*' or '**' inside preparation steps text.\n"
            "5. KBHU: Estimated data PER SERVING.\n"
            "6. CULINARY TRIAD: Add 'Chef's Advice' based on Taste, Aroma, Texture. "
            "Recommend EXACTLY ONE missing item to finish the triad.\n\n"
            f"STRUCTURE IN {target_lang.upper()}:\n"
            "🥘 [Dish Name]\n\n"
            "📦 Ингредиенты:\n[Item list with amounts - NO EMOJIS HERE]\n\n"
            "📊 КБЖУ на порцию:\n[Data]\n\n"
            "⏱ Время: [min] | 📈 Сложность: [level] | 👥 Порции: [num]\n\n"
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
            "Dangerous/Prohibited -> '⛔ Only food recipes here.'"
        )
        res = await GroqService._send_groq_request(prompt, dish_name, 0.7)
        return res

    @staticmethod
    def _is_refusal(text: str) -> bool:
        refusals = ["cannot fulfill", "against my policy", "не могу ответить", "извините", "⛔"]
        return any(ph in text.lower() for ph in refusals)