from groq import AsyncGroq  # Асинхронный клиент
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from typing import Dict
import json

# Инициализируем асинхронного клиента
client = AsyncGroq(api_key=GROQ_API_KEY)

class GroqService:
    @staticmethod
    async def generate_dishes(products: str) -> str:
        prompt = f"""У пользователя есть: {products}
Предложи 3-5 блюд.
Формат:
🍽️ Название
Описание - время.

В конце добавь: '🎤 Добавьте продукты или назовите блюдо для получения рецепта'."""

        # Используем await!
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.7
        )
        return response.choices[0].message.content
    
    @staticmethod
    async def determine_intent(user_message: str, dish_list: str) -> Dict:
        prompt = f"""История: {dish_list}
Юзер: "{user_message}"
Верни JSON: {{"intent": "select_dish"|"add_products"|"unclear", "dish_name": "...", "products": "..."}}"""

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1 # Меньше фантазии для JSON
        )
        
        result = response.choices[0].message.content.strip()
        if result.startswith("```"):
            result = result.split("```")[1].strip()
            if result.startswith("json"):
                result = result[4:].strip()
        
        try:
            return json.loads(result)
        except:
            return {"intent": "unclear"}
    
    @staticmethod
    async def generate_recipe(dish_name: str, products: str) -> str:
        prompt = f"Рецепт: {dish_name}. Продукты: {products}. Детально."

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.7
        )
        return response.choices[0].message.content
