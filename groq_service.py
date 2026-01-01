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
    def _extract_json(text: str) -> Union[Dict, List, None]:
        """Безопасное извлечение JSON из любого места в тексте."""
        if not text: return None
        try:
            start_idx = min([text.find(c) for c in '{[' if text.find(c) != -1] or [-1])
            if start_idx == -1: return None
            end_char = '}' if text[start_idx] == '{' else ']'
            end_idx = text.rfind(end_char)
            if end_idx == -1: return None
            return json.loads(text[start_idx:end_idx + 1])
        except:
            match = re.search(r'(?s)(\{.*\}|\[.*\])', text)
            if match:
                try: return json.loads(match.group())
                except: return None
        return None

    @staticmethod
    async def determine_intent(text: str) -> Dict[str, str]:
        """Определяет: список продуктов это или запрос конкретного рецепта."""
        prompt = (
            "Analyze input. Return ONLY JSON: "
            "{\"intent\": \"ingredients\"} or {\"intent\": \"recipe\", \"dish\": \"name\"}."
        )
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        
        # Fallback на случай ошибки AI или формата
        if not data or "intent" not in data:
            text_l = text.lower()
            keywords = ['рецепт', 'recipe', 'как приготовить', 'приготовь']
            if any(kw in text_l for kw in keywords):
                dish = text
                for kw in keywords: dish = dish.replace(kw, "")
                return {"intent": "recipe", "dish": dish.strip()}
            return {"intent": "ingredients"}
        return data

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        """Проверка, что на входе именно еда."""
        prompt = "Return ONLY JSON: {\"valid\": true} if input is food, else {\"valid\": false}."
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        return data.get("valid", True) if data else True

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        """Определяет подходящие категории блюд."""
        prompt = (
            "Analyze ingredients. Return ONLY a JSON array of keys: "
            "['soup', 'main', 'salad', 'breakfast', 'dessert', 'drink', 'snack'].\n"
            "Rule: If broth possible (water+vegetables), include 'soup'."
        )
        res = await GroqService._send_groq_request(prompt, products, 0.2)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else ["main", "snack"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str, style: str = "обычный", lang_code: str = "ru") -> List[Dict[str, str]]:
        """Генерирует список из 4-6 вариантов блюд."""
        target_lang = "Russian" if lang_code[:2].lower() == "ru" else "English"
        system_prompt = (
            f"Chef mode. Suggest 4-6 dishes in category '{category}' for style '{style}'.\n"
            f"RULES: 1. Field 'name': Native language. 2. Field 'desc': {target_lang}.\n"
            f"3. Field 'display_name': 'Original (Translation)' ONLY if original is not {target_lang}.\n"
            f"Return ONLY JSON: [{{'name': '...', 'display_name': '...', 'desc': '...'}}]."
        )
        res = await GroqService._send_groq_request(system_prompt, f"Ingredients: {products}", 0.6)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, lang_code: str = "ru") -> str:
        """Генерация детального рецепта с КБЖУ и Триадой Шефа."""
        target_lang = "Russian" if lang_code[:2].lower() == "ru" else "English"
        
        system_prompt = (
            f"Professional chef. Write a recipe in {target_lang}.\n"
            f"STRICT RULES:\n"
            f"1. NAME: Original Native name.\n"
            f"2. SILENT EXCLUSION: Use ONLY user products + BASICS (water, salt, oil, sugar, pepper). "
            f"NEVER mention what you DID NOT use.\n"
            f"3. INGREDIENTS: Format '- Item - Amount'. Bilingual ONLY if original is not {target_lang}.\n"
            f"4. NUTRITION: Calculate per serving. Use emojis: 📊, 🥚, 🥑, 🌾, ⚡.\n"
            f"5. CULINARY TRIAD: End with 'Chef's Advice' analyzing Taste, Aroma, Texture.\n"
            f"6. NO EMOJIS in steps. No bold '**' in steps.\n\n"
            "STRUCTURE: 🥘 [Name]\n\n📦 Ингредиенты:\n[List]\n\n📊 Пищевая ценность...\n\n⏱ Время | 🎚 Сложность | 👥 Порции\n\n🔪 Приготовление:\n[Steps]\n\n💡 Совет шеф-повара:"
        )

        res = await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Products: {products}", 0.3)
        
        if GroqService._is_refusal(res): return res

        bon = "Приятного аппетита!" if lang_code == "ru" else "Bon appétit!"
        return f"{res}\n\n👨‍🍳 <b>{bon}</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str, lang_code: str = "ru") -> str:
        target_lang = "Russian" if lang_code[:2].lower() == "ru" else "English"
        prompt = f"Recipe for {dish_name} in {target_lang}. Safety: return ⛔ if unsafe."
        res = await GroqService._send_groq_request(prompt, "", 0.7)
        return res

    @staticmethod
    def _is_refusal(text: str) -> bool:
        return any(ph in text.lower() for ph in ["cannot fulfill", "извините", "⛔"])
