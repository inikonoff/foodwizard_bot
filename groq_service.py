from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from typing import Dict
import json

client = AsyncGroq(api_key=GROQ_API_KEY)

class GroqService:
    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        """
        Проверяет, является ли текст списком существенных продуктов.
        """
        prompt = f"""Анализируй текст: "{text}"

        Твоя задача определить, перечислил ли пользователь СУЩЕСТВЕННЫЕ продукты для готовки.
        
        Верни JSON: {{"valid": true}} ЕСЛИ:
        - В тексте есть овощи, фрукты, мясо, рыба, крупы, молочка, консервы и т.д.
        
        Верни JSON: {{"valid": false}} ЕСЛИ:
        - Текст бессмысленный (набор букв, опечатки типа "мпасибо").
        - Это приветствие ("привет", "хай") или благодарность ("спасибо").
        - Перечислены ТОЛЬКО базовые расходники (соль, вода, перец, масло, сахар, лед). Готовить только из них нельзя.

        ВЕРНИ ТОЛЬКО JSON."""

        try:
            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.1
            )
            
            raw = response.choices[0].message.content.strip()
            
            # Простой парсинг
            if "true" in raw.lower(): return True
            if "false" in raw.lower(): return False
            
            # JSON парсинг
            start = raw.find('{')
            end = raw.rfind('}')
            if start != -1 and end != -1:
                data = json.loads(raw[start : end + 1])
                return data.get("valid", False)
            
            return False
        except Exception:
            return False

    @staticmethod
    async def generate_dishes(products: str, style: str = "обычный") -> str:
        prompt = f"""У пользователя есть продукты: {products}.
        Базовые продукты (всегда есть): соль, перец, вода, растительное масло.

        Твоя роль: Опытный шеф-повар, специалист по домашней кухне.
        Задача: Предложи 8-10 реалистичных блюд в стиле: "{style}".

        КУЛИНАРНЫЕ ПРАВИЛА (строго соблюдать):
        1. ВКУС И СОЧЕТАЕМОСТЬ - главный приоритет. Предлагай только проверенные, аппетитные комбинации.
        2. ЗАПРЕЩЕНО комбинировать:
        - Рыбу с мясом или салом
        - Молочное с солеными/ маринованными продуктами (огурцы, селедка, цитрусы)
        - Сладкие фрукты с чесноком, луком или острым
        3. Если есть несколько белковых продуктов (рыба, мясо, птица) - делай для каждого ОТДЕЛЬНОЕ блюдо.
        4. Используй продукты из списка разумно: лучше вкусное блюдо из 3 продуктов, чем странное из 7.
        5. Если для хорошего рецепта не хватает 1-2 продуктов - укажи в скобках: "(+ недостающее)".

        Формат ответа:
        🍽️ Название блюда
        Краткое, лаконичное и аппетитное описание - примерное время.

        В конце добавь: '🎤 Выберите блюдо или добавьте продукты'."""

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.5
        )
        return response.choices[0].message.content
    
    @staticmethod
    async def determine_intent(user_message: str, dish_list: str) -> Dict:
        prompt = f"""Контекст (предложенные блюда):
        {dish_list}
        Сообщение пользователя: "{user_message}"
        Задача: определить намерение.
        1. Называет блюдо -> "select_dish"
        2. Добавляет продукты -> "add_products"
        3. Непонятно -> "unclear"
        ВЕРНИ ТОЛЬКО JSON."""

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2
        )
        
        raw_result = response.choices[0].message.content.strip()
        try:
            start_index = raw_result.find('{')
            end_index = raw_result.rfind('}')
            if start_index != -1 and end_index != -1:
                return json.loads(raw_result[start_index : end_index + 1])
            else:
                return {"intent": "unclear"}
        except Exception:
            return {"intent": "unclear"}
            
    @staticmethod
    async def generate_recipe(dish_name: str, products: str) -> str:
        prompt = f"""Напиши подробный рецепт: "{dish_name}".
        Доступные продукты: {products}.
        Задача: РЕАЛИСТИЧНЫЙ и ВКУСНЫЙ рецепт.
        
        Формат:
        🍽️ [Название]
        🛒 Ингредиенты: (Пометь ✅ есть, 🛒 докупить)
        👨‍🍳 Приготовление: (по шагам)"""

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.5
        )
        
        recipe_text = response.choices[0].message.content
        return recipe_text + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str) -> str:
        prompt = f"""Напиши классный рецепт блюда: "{dish_name}".
        Пиши с душой, как шеф-повар, но естественно и не приторно и без подхалимажа"""

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.6
        )
        
        recipe_text = response.choices[0].message.content
        return recipe_text + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"
