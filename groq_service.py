from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from typing import Dict, List, Union
import json
import re
import logging

client = AsyncGroq(api_key=GROQ_API_KEY)
logger = logging.getLogger(__name__)

class GroqService:
    
    # --- БАЗОВЫЙ МЕТОД ЗАПРОСА ---
    @staticmethod
    async def _send_groq_request(system_prompt: str, user_text: str, temperature: float = 0.5, max_tokens: int = 1000) -> str:
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

    # --- ЛОГИКА ---

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        prompt = """Твоя задача — модерация списка продуктов.
        Верни JSON: {"valid": true} ЕСЛИ в тексте съедобные продукты.
        Верни JSON: {"valid": false} ЕСЛИ бессмыслица, приветствия или несъедобные/опасные предметы.
        ВЕРНИ ТОЛЬКО JSON."""
        
        res = await GroqService._send_groq_request(prompt, f"Анализируй: \"{text}\"", 0.1)
        return "true" in res.lower()

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        """
        Определяет, какие категории блюд из этого РЕАЛЬНО приготовить.
        Возвращает список ключей: ['soup', 'main', 'salad', 'dessert', 'drink', 'snack']
        """
        prompt = f"""Ты опытный шеф-повар. Проанализируй список продуктов: "{products}".
        
        Определи, какие категории блюд из этого РЕАЛЬНО приготовить (имея базовые соль/воду/масло).
        
        Возможные категории:
        - "soup" (супы)
        - "main" (вторые блюда)
        - "salad" (салаты)
        - "breakfast" (завтраки)
        - "dessert" (десерты - только если есть сахар/фрукты/мука)
        - "drink" (напитки - смузи, морсы, коктейли - если есть фрукты/молоко/ягоды)
        - "snack" (закуски)
        
        ВЕРНИ ТОЛЬКО JSON список ключей. Если продуктов очень мало, верни только самую подходящую категорию.
        Пример: ["main", "salad", "drink"]
        """
        
        res = await GroqService._send_groq_request(prompt, "Анализируй категории", 0.2)
        
        try:
            # Очистка от маркдауна, который любит Groq
            clean_json = res.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.error(f"Category JSON Error: {e}")
            pass
        
        # Fallback, если что-то пошло не так
        return ["main"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str, style: str = "обычный") -> List[Dict[str, str]]:
        """
        Генерирует список блюд. Количество зависит от обилия продуктов.
        """
        # Умный подсчет ингредиентов
        items_count = len(re.split(r'[,]', products))
        
        if items_count <= 2:
            target_count = "2-3"
            complexity = "простых"
        elif items_count <= 5:
            target_count = "4-5"
            complexity = "разнообразных"
        else:
            target_count = "5-6" # Максимум 6 для экрана телефона
            complexity = "интересных"

        # Карта названий
        cat_names = {
            "soup": "Супы", "main": "Вторые блюда", "salad": "Салаты",
            "breakfast": "Завтраки", "dessert": "Десерты", "drink": "Напитки", "snack": "Закуски"
        }
        cat_ru = cat_names.get(category, "Блюда")

        prompt = f"""Ты шеф-повар. Продукты: {products}.
        Задача: Придумай {target_count} {complexity} блюд в категории: "{cat_ru}". Стиль: {style}.
        
        Если категория "Напитки" - предлагай смузи, морсы, коктейли.
        
        ВЕРНИ СТРОГО JSON формат (список объектов), без лишних слов:
        [
            {{"name": "Название блюда", "desc": "Краткое описание"}}
        ]
        """
        
        res = await GroqService._send_groq_request(prompt, "Предложи меню JSON", 0.5)
        
        try:
            clean_json = res.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.error(f"Dishes JSON Error: {e}")
        return []

    @staticmethod
    async def determine_intent(user_message: str, dish_list: str) -> Dict:
        prompt = f"""Контекст: {dish_list}
        Сообщение: "{user_message}"
        Определи намерение:
        1. "add_products" (добавил продукты, изменил условия)
        2. "select_dish" (назвал блюдо текстом)
        3. "unclear"
        JSON: {{"intent": "...", "products": "...", "dish_name": "..."}}"""

        res = await GroqService._send_groq_request(prompt, "Анализируй", 0.1)
        
        try:
            start = res.find('{')
            end = res.rfind('}')
            if start != -1 and end != -1:
                return json.loads(res[start : end + 1])
        except Exception:
            pass
        return {"intent": "unclear"}
            
    @staticmethod
    async def generate_recipe(dish_name: str, products: str) -> str:
        prompt = f"""Напиши подробный рецепт: "{dish_name}".
        Доступные продукты: {products}.
        
        Формат:
        🍽️ [Название]
        🛒 Ингредиенты: (Пометь ✅ есть, 🛒 докупить)
        👨‍🍳 Приготовление: (по шагам)"""

        res = await GroqService._send_groq_request(prompt, "Напиши рецепт", 0.4)
        if GroqService._is_refusal(res): return res
        return res + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str) -> str:
        prompt = f"""Пользователь просит рецепт: "{dish_name}".
        
        ПРАВИЛА БЕЗОПАСНОСТИ:
        1. Если это ЕДА -> Пиши вкусный рецепт.
        2. Если это АБСТРАКЦИЯ (счастье, любовь) -> Пиши метафорический рецепт.
        3. Если это ОПАСНОЕ/ЗАПРЕЩЕННОЕ (наркотики, оружие, яды, насилие) -> 
           Ответь СТРОГО: "⛔ Извините, я готовлю только еду."
        """

        res = await GroqService._send_groq_request(prompt, "Напиши рецепт", 0.6)
        if GroqService._is_refusal(res): return res
        return res + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    def _is_refusal(text: str) -> bool:
        if "⛔" in text: return True
        refusals = ["cannot fulfill", "cannot answer", "against my policy", "не могу ответить", "нарушает правила"]
        for ph in refusals:
            if ph in text.lower(): return True
        return False
