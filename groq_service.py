import json
import re
import logging
import asyncio
from typing import Dict, List, Union, Optional
from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL
from culinary_map import get_cuisine_for_lang, get_lang_name

client = AsyncGroq(api_key=GROQ_API_KEY)
logger = logging.getLogger(__name__)

class GroqService:
    # Базовый набор продуктов, доступный всегда
    KITCHEN_BASE = "соль, сахар, вода, подсолнечное масло, специи"

    # --- СИСТЕМНЫЕ МЕТОДЫ ---

    @staticmethod
    async def _send_groq_request(system_prompt: str, user_text: str, temperature: float = 0.5, max_tokens: int = 1500) -> Optional[str]:
        """Централизованный метод запроса с обработкой таймаутов и ошибок"""
        try:
            # Добавлен таймаут для предотвращения бесконечного ожидания
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature
                ),
                timeout=30.0
            )
            content = response.choices[0].message.content
            return content.strip() if content else None
        except asyncio.TimeoutError:
            logger.error("Groq API Timeout")
        except Exception as e:
            logger.error(f"Groq API Error: {e}")
        return None

    @staticmethod
    def _extract_json(text: str) -> str:
        """Извлекает JSON из текста, удаляя артефакты разметки"""
        if not text: return ""
        # Очистка от markdown блоков
        text = re.sub(r'```json\s*|```', '', text).strip()
        
        start_idx = text.find('[') if '[' in text and ('{' not in text or text.find('[') < text.find('{')) else text.find('{')
        end_idx = text.rfind(']') if ']' in text and ('}' not in text or text.rfind(']') > text.rfind('}')) else text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            return text[start_idx:end_idx + 1]
        return text

    @staticmethod
    def _safe_deserialize(json_str: str, default_value: Union[dict, list]) -> Union[dict, list]:
        """Безопасная десериализация с логированием"""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON: {json_str[:200]}...")
            return default_value

    @staticmethod
    def _is_refusal(text: str) -> bool:
        """Проверка на отказ ИИ отвечать"""
        if not text: return True
        refusal_markers = ["cannot fulfill", "against my policy", "не могу выполнить", "извините, но я", "⛔"]
        return any(marker in text.lower() for marker in refusal_markers)

    # --- БИЗНЕС-ЛОГИКА ---

    @staticmethod
    async def detect_products_language(products: str) -> str:
        prompt = """Определи язык текста. Верни ТОЛЬКО двухбуквенный код (ISO 639-1). 
        Если не уверен или язык русский — 'ru'."""
        res = await GroqService._send_groq_request(prompt, products, 0.1, 10)
        if not res: return "ru"
        
        code = res.strip().lower()[:2]
        valid_codes = {"ru", "en", "es", "fr", "it", "de", "zh", "ja", "ko", "uk", "pl", "tr", "ar", "he", "hi", "th", "vi"}
        return code if code in valid_codes else "ru"

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        prompt = f"""Ты эксперт по безопасности. Проверь, являются ли вводные данные съедобными продуктами.
        Ответь строго JSON: {{"valid": true, "reason": "..."}} или {{"valid": false, "reason": "..."}}"""
        
        res = await GroqService._send_groq_request(prompt, text, 0.1, 100)
        if not res: return True # По умолчанию пропускаем при ошибке сети
        
        data = GroqService._safe_deserialize(GroqService._extract_json(res), {"valid": True})
        return data.get("valid", True)

    @staticmethod
    async def analyze_categories(products: str, products_lang: str) -> List[str]:
        items_count = len(re.split(r'[,;]', products))
        allow_mix = items_count >= 5
        cuisine = get_cuisine_for_lang(products_lang)
        
        prompt = f"""Определи 1-3 категории блюд для продуктов: {products}.
        Кухня: {cuisine}. База: {GroqService.KITCHEN_BASE}.
        Доступные категории: soup, main, salad, breakfast, dessert, drink, snack{', mix' if allow_mix else ''}.
        Верни ТОЛЬКО JSON список строк: ["cat1", "cat2"]"""
        
        res = await GroqService._send_groq_request(prompt, "Анализ", 0.2, 100)
        categories = GroqService._safe_deserialize(GroqService._extract_json(res), ["main"])
        
        # Фильтрация mix, если продуктов мало
        if "mix" in categories and not allow_mix:
            categories = [c for c in categories if c != "mix"] or ["main"]
        return categories

    @staticmethod
    async def generate_dishes_list(products: str, category: str, style: str, products_lang: str) -> List[Dict[str, str]]:
        target_count = 2 if len(products.split(',')) <= 2 else 4
        cuisine = get_cuisine_for_lang(products_lang)
        lang_name = get_lang_name(products_lang)

        instruction = (
            f"Названия на {lang_name}, описания на РУССКОМ." 
            if products_lang != "ru" else "Все на русском."
        )

        prompt = f"""Составь меню из {target_count} блюд. Категория: {category}. Кухня: {cuisine}.
        Используй только: {products} + {GroqService.KITCHEN_BASE}.
        {instruction}
        Формат JSON: [{{"name": "...", "desc": "..."}}]"""
        
        res = await GroqService._send_groq_request(prompt, "Меню", 0.6, 1000)
        return GroqService._safe_deserialize(GroqService._extract_json(res), [])

    @staticmethod
    async def generate_recipe(dish_name: str, products: str, products_lang: str) -> str:
        lang_name = get_lang_name(products_lang)
        is_ru = products_lang == "ru"
        
        prompt = f"""Напиши подробный рецепт для: {dish_name}.
        Продукты: {products}, База: {GroqService.KITCHEN_BASE}.
        Язык: Заголовок на {lang_name}, остальное на РУССКОМ.
        Включи: Ингредиенты, КБЖУ, Время, Сложность, Шаги и 'Совет шефа' (Вкус/Аромат/Текстура)."""

        res = await GroqService._send_groq_request(prompt, "Рецепт", 0.4, 2000)
        if not res or GroqService._is_refusal(res):
            return "К сожалению, я не могу составить рецепт для этого запроса. 😔"
        
        return f"{res}\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str) -> str:
        prompt = f"""Создай креативный рецепт: {dish_name}.
        Если это еда — обычный рецепт. Если абстракция — кулинарная метафора.
        Все на РУССКОМ языке. Используй формат: Название, Ингредиенты, Приготовление, Совет."""
        
        res = await GroqService._send_groq_request(prompt, "Креатив", 0.7, 2000)
        if not res or GroqService._is_refusal(res):
            return "Мои половники запутались... Не могу создать этот рецепт. 🥣"
            
        return f"{res}\n\n👨‍🍳 <b>Приятного аппетита!</b>"