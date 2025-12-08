from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from typing import Dict
import json

# Инициализируем асинхронного клиента
client = AsyncGroq(api_key=GROQ_API_KEY)

class GroqService:
    @staticmethod
    async def generate_dishes(products: str, style: str = "обычный") -> str:
        """
        Генерирует блюда с учетом стиля.
        """
        prompt = f"""У пользователя есть продукты: {products}.
        Базовые продукты (всегда есть): соль, перец, вода, растительное масло, сахар.

        Задача: Предложи 8-10 вариантов блюд в стиле: "{style}".

        СТРОГИЕ ПРАВИЛА:
        1. Используй НЕ МЕНЕЕ 50% перечисленных пользователем продуктов.
        2. Приоритет — рецепты, где все продукты есть в наличии.
        3. Если для крутого рецепта не хватает 1-2 ингредиентов, всё равно предложи его, но в названии ОБЯЗАТЕЛЬНО укажи: "Название (докупить: ...)".
        4. Если стиль "экзотический" — предлагай необычные сочетания.
        5. Если стиль "простой" — предлагай домашнюю классику.

        Формат ответа:
        🍽️ Название блюда [нюансы] - время.

        В конце добавь: '🎤 Назовите блюдо или добавьте продукты'."""

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.6
        )
        return response.choices[0].message.content
    
    @staticmethod
    async def determine_intent(user_message: str, dish_list: str) -> Dict:
        """
        Определяет намерение пользователя.
        Теперь с более надежным парсингом.
        """
        prompt = f"""Контекст (предложенные блюда):
        {dish_list}

        Сообщение пользователя: "{user_message}"

        Твоя задача определить, что хочет пользователь:
        1. Если он называет блюдо из списка (или похожее) -> "select_dish".
        2. Если он пишет названия новых продуктов (например: "еще есть лук", "добавь хлеб", "помидоры") -> "add_products".
        3. Если непонятно -> "unclear".

        ВЕРНИ ТОЛЬКО JSON. Никаких слов "Вот json" или markdown.
        Пример: {{"intent": "select_dish", "dish_name": "Борщ"}}
        Пример: {{"intent": "add_products", "products": "лук, морковь"}}
        """

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1 # Минимум фантазии
        )
        
        raw_result = response.choices[0].message.content.strip()
        print(f"DEBUG GROQ: {raw_result}") # В логах Render можно будет увидеть, что ответила сеть

        # --- ПУЛЕНЕПРОБИВАЕМЫЙ ПАРСИНГ JSON ---
        try:
            # Ищем первую открывающую { и последнюю закрывающую }
            start_index = raw_result.find('{')
            end_index = raw_result.rfind('}')
            
            if start_index != -1 and end_index != -1:
                json_str = raw_result[start_index : end_index + 1]
                return json.loads(json_str)
            else:
                return {"intent": "unclear"}
        except Exception as e:
            print(f"JSON Parse Error: {e}")
            return {"intent": "unclear"}
            
    @staticmethod
    async def generate_recipe(dish_name: str, products: str) -> str:
        prompt = f"""Напиши подробный рецепт: "{dish_name}".
        Доступные продукты пользователя: {products}.
        Базовые (всегда есть): вода, масло, соль, перец.
        
        Если в названии блюда было "(докупить: ...)", включи эти продукты в состав.

        Формат:
        🍽️ [Название]
        
        🛒 Ингредиенты:
        (Пометь ✅ то, что у пользователя есть, и 🛒 то, что нужно докупить)

        👨‍🍳 Приготовление:
        1. ...
        2. ...
        """

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.7
        )
        return response.choices[0].message.content

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str) -> str:
        prompt = f"""Напиши классный рецепт блюда: "{dish_name}".
        Пиши с душой, как шеф-повар.
        Структура: Ингредиенты, Шаги."""

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.7
        )
        return response.choices[0].message.content
