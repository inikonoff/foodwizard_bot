from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from typing import Dict, List, Union
import json
import re
import logging

client = AsyncGroq(api_key=GROQ_API_KEY)
logger = logging.getLogger(__name__)

class GroqService:
    
    LANG_CODES = {
        'ru': 'Russian', 'en': 'English', 'es': 'Spanish',
        'fr': 'French', 'de': 'German', 'it': 'Italian'
    }
    
    BASIC_INGREDIENTS = {
        'ru': ['вода', 'соль', 'растительное масло', 'сахар', 'перец', 'лед'],
        'en': ['water', 'salt', 'vegetable oil', 'sugar', 'pepper', 'ice'],
        'es': ['agua', 'sal', 'aceite vegetal', 'azúcar', 'pimienta', 'hielo']
    }
    
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
        """Универсальный и безопасный извлекатель JSON."""
        if not text: return None
        try:
            # Поиск самого широкого блока
            start_idx = min([text.find(c) for c in '{[' if text.find(c) != -1] or [-1])
            if start_idx == -1: return None
            end_char = '}' if text[start_idx] == '{' else ']'
            end_idx = text.rfind(end_char)
            if end_idx == -1: return None
            return json.loads(text[start_idx:end_idx + 1])
        except:
            # Fallback через регулярку
            match = re.search(r'(?s)(\{.*\}|\[.*\])', text)
            if match:
                try: return json.loads(match.group())
                except: return None
        return None

    @staticmethod
    def _detect_input_language(text: str) -> str:
        """Определяет язык ввода для подбора базовых продуктов."""
        text_l = text.lower()
        markers = {
            'ru': ['карто', 'лук', 'морков', 'соль', 'сахар'],
            'en': ['potato', 'onion', 'carrot', 'salt', 'sugar']
        }
        for lang, kws in markers.items():
            if any(kw in text_l for kw in kws): return lang
        return 'ru'

    @staticmethod
    async def determine_intent(text: str, last_context: str = "") -> Dict[str, str]:
        """Определяет намерение: продукты или рецепт конкретного блюда."""
        input_lang = GroqService._detect_input_language(text)
        prompt = (
            "Analyze input. Return ONLY JSON: "
            "{\"intent\": \"ingredients\"} or {\"intent\": \"recipe\", \"dish\": \"name\"}."
        )
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        
        if not data or "intent" not in data:
            # Fallback на ключевые слова
            if any(kw in text.lower() for kw in ['рецепт', 'recipe', 'как приготовить']):
                return {"intent": "recipe", "dish": text, "input_lang": input_lang}
            return {"intent": "ingredients", "input_lang": input_lang}
        
        data["input_lang"] = input_lang
        return data

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        prompt = "Return ONLY JSON: {\"valid\": true} if input is food items, else {\"valid\": false}."
        res = await GroqService._send_groq_request(prompt, text, 0.1)
        data = GroqService._extract_json(res)
        return data.get("valid", True) if data else True

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        input_lang = GroqService._detect_input_language(products)
        basics = GroqService.BASIC_INGREDIENTS.get(input_lang, GroqService.BASIC_INGREDIENTS['ru'])
        
        prompt = (
            f"Analyze ingredients: {products}. Basics available: {basics}. "
            "Return ONLY JSON array of keys from: ['soup', 'main', 'salad', 'breakfast', 'dessert', 'drink', 'snack']. "
            "RULES: 1. Fruit/ice -> 'drink'. 2. Flour/sugar/fruit -> 'dessert', 'breakfast'. 3. Min 3 categories."
        )
        res = await GroqService._send_groq_request(prompt, "", 0.2)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else ["main", "snack"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str, style: str = "обычный", 
                                   interface_lang: str = "ru", input_lang: str = "ru") -> List[Dict[str, str]]:
        target_lang = GroqService.LANG_CODES.get(interface_lang, 'Russian')
        
        system_prompt = (
            f"Chef mode. Suggest 4-6 dishes in category '{category}'. "
            f"RULES: 1. 'name': Native language. 2. 'desc': {target_lang}. "
            f"3. 'display_name': 'Original (Translation)' ONLY if original is not {target_lang}. "
            f"Return ONLY JSON list: [{{'name': '...', 'display_name': '...', 'desc': '...'}}]."
        )
        res = await GroqService._send_groq_request(system_prompt, f"Ingredients: {products}", 0.6)
        data = GroqService._extract_json(res)
        return data if isinstance(data, list) else []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, interface_lang: str = "ru", input_lang: str = "ru") -> str:
        """Генерация рецепта с Триадой: Вкус, Аромат, Текстура."""
        target_lang = GroqService.LANG_CODES.get(interface_lang, 'Russian')
        basics = GroqService.BASIC_INGREDIENTS.get(interface_lang, GroqService.BASIC_INGREDIENTS['ru'])
        
        system_prompt = f"""You are a professional chef. Write a recipe in {target_lang}.
        
        STRICT RULES:
        1. NAME: Original Native name in header.
        2. INGREDIENTS: Bilingual format 'Native (Translation) - amount' ONLY if native is not {target_lang}. Else 'Name - amount'.
        3. SILENT EXCLUSION: Never mention or explain why an ingredient from the user list is NOT used.
        4. CULINARY TRIAD (Chef's Tip): Analyze the dish by TASTE, AROMA, and TEXTURE. 
           Recommend exactly one missing item from Culinary Trinity or French Mirepoix to improve the triad.
        5. NO EMOJIS in steps. No bold '**' formatting in steps.

        STRUCTURE:
        🥘 [Original Name]
        
        📦 ИНГРЕДИЕНТЫ:
        - [List]
        
        📊 ПИЩЕВАЯ ЦЕННОСТЬ (1 порция):
        🥚 Белки: X г | 🥑 Жиры: X г | 🌾 Углеводы: X г | ⚡ Калории: X ккал
        
        ⏱ Время: X мин | 🎚 Сложность: X/5 | 👥 Порции: X
        
        🔪 ПРИГОТОВЛЕНИЕ:
        [Numbered steps]

        💡 СОВЕТ ШЕФА (КУЛИНАРНАЯ ТРИАДА):
        [Professional analysis of Taste, Aroma, Texture]"""
        
        res = await GroqService._send_groq_request(system_prompt, f"Dish: {dish_name}. Products: {products}", 0.3)
        
        farewells = {'ru': 'Приятного аппетита!', 'en': 'Bon appétit!'}
        bon = farewells.get(interface_lang, "Bon appétit!")
        return f"{res}\n\n👨‍🍳 **{bon}**"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str, interface_lang: str = "ru") -> str:
        prompt = f"Write recipe for {dish_name} in {GroqService.LANG_CODES.get(interface_lang)}. Safety: return ⛔ if unsafe."
        res = await GroqService._send_groq_request(prompt, "", 0.7)
        return res if "⛔" not in res else "⛔ Некорректный запрос."

    @staticmethod
    def _is_refusal(text: str) -> bool:
        return any(p in text.lower() for p in ["cannot fulfill", "извините", "⛔"])