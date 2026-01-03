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
        Определяет доступные категории.
        Mix включается только если продуктов >= 5.
        """
        items_count = len(re.split(r'[,;]', products))
        allow_mix = items_count >= 5
        mix_prompt = "- 'mix' (комплексный обед - сет из 2-3 блюд)" if allow_mix else ""

        prompt = f"""Ты опытный шеф-повар. Проанализируй продукты: "{products}".
        Определи категории блюд, которые РЕАЛЬНО приготовить (база: соль/вода/масло/сахар есть).
           
        Категории:
        - "soup" (супы)
        - "main" (вторые блюда)
        - "salad" (салаты)
        - "breakfast" (завтраки)
        - "dessert" (десерты - если есть сахар/мука/фрукты)
        - "drink" (напитки)
        - "snack" (закуски)
        {mix_prompt}
        
        Если продуктов мало - верни 1-2 категории. Если много - 3-4.
        ВЕРНИ ТОЛЬКО JSON список ключей.
        """
        
        res = await GroqService._send_groq_request(prompt, "Анализируй", 0.2)
        
        try:
            clean_json = res.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            if isinstance(data, list):
                if "mix" in data and not allow_mix:
                    data.remove("mix")
                return data
        except Exception:
            pass
        return ["main"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str) -> List[Dict[str, str]]:
        """
        Генерирует список блюд или сетов.
        """
        items_count = len(re.split(r'[,]', products))
        target_count = "2-3" if items_count <= 2 else ("4-5" if items_count <= 5 else "5-6")

        cat_names = {
            "soup": "Супы", "main": "Вторые блюда", "salad": "Салаты", 
            "breakfast": "Завтраки", "dessert": "Десерты", "drink": "Напитки", 
            "snack": "Закуски", "mix": "Комплексные обеды"
        }
        cat_ru = cat_names.get(category, "Блюда")

        if category == "mix":
            prompt = f"""📝 ЗАДАНИЕ: Составь меню "Комплексный обед" (Mix).
            🛒 ПРОДУКТЫ: {products}
            🔢 Количество: {target_count} вариантов.
            
            Каждый вариант — это СЕТ из 2-3 сочетающихся блюд (напр. Суп + Салат).
            
            ФОРМАТ JSON:
            [
                {{"name": "Название сета", "desc": "Состав: [Блюдо 1] + [Блюдо 2]. Описание."}}
            ]
            """
        else:
            prompt = f"""📝 ЗАДАНИЕ: Предложи меню категории "{cat_ru}".
            🛒 ПРОДУКТЫ: {products}
            🔢 Количество: {target_count} вариантов.
            
            ФОРМАТ JSON:
            [
                {{"name": "Название блюда", "desc": "Аппетитное описание"}}
            ]
            """
        
        res = await GroqService._send_groq_request(prompt, "JSON меню", 0.5)
        
        try:
            clean_json = res.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.error(f"Dishes JSON Error: {e}")
        return []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str) -> str:
        """
        Генерирует рецепт в строгом формате со скриншотов.
        """
        is_mix = any(x in dish_name.lower() for x in ["обед", "сет", "комплекс", "+"])
        
        mix_instruction = ""
        if is_mix:
            mix_instruction = "ЭТО СЕТ. Распредели продукты между блюдами. Не дублируй мясо/основу."

        prompt = f"""Ты профессиональный шеф. Напиши рецепт: "{dish_name}".
        
        🛒 ПРОДУКТЫ: {products}
        (База: соль, вода, масло, специи).
        {mix_instruction}

         СТРОГИЙ ФОРМАТ ОТВЕТА (следуй визуальному стилю):
        
        [Название блюда]
        
        📦 Ингредиенты:
        - [продукт] — [кол-во]
        - [продукт] — [кол-во]
        (Если сет — делай подзаголовки, но используй тире для списков)

        📊 Пищевая ценность на 1 порцию:
        🥚 Белки: X г
        🥑 Жиры: X г
        🌾 Углеводы: X г
        ⚡ Энерг. ценность: X ккал

        ⏱ Время: X минут
        🎚 Сложность: [легкая/средняя/сложная]
        👥 Порции: X чел.

        👨‍🍳 Приготовление:
        1. ...
        2. ...

        💡 СОВЕТ ШЕФ-ПОВАРА (КУЛИНАРНАЯ ТРИАДА):
        Analyze Taste, Aroma, and Texture in Russian. Recommend ONE element to balance the triad.
        (Пример: "Блюду не хватает хруста. Добавьте сухарики.")
        """

        res = await GroqService._send_groq_request(prompt, "Напиши рецепт", 0.4)
        if GroqService._is_refusal(res): 
            return res
        return res + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str) -> str:
        prompt = f"""Рецепт: "{dish_name}".
        Если еда — формат с КБЖУ (🥚, 🥑, 🌾, ⚡) и ингредиентами через тире (-).
        Если метафора — философский рецепт.
        """
        res = await GroqService._send_groq_request(prompt, "Рецепт", 0.6)
        if GroqService._is_refusal(res): return res
        return res + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    def _is_refusal(text: str) -> bool:
        if "⛔" in text: return True
        refusals = ["cannot fulfill", "cannot answer", "against my policy"]
        for ph in refusals:
            if ph in text.lower(): return True
        return False