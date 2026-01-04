from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL
from typing import Dict, List, Optional
import json
import re
import logging

client = AsyncGroq(api_key=GROQ_API_KEY)
logger = logging.getLogger(__name__)

class GroqService:
    
    LLM_CONFIG = {
        "validation": {"temperature": 0.1, "max_tokens": 200},
        "categorization": {"temperature": 0.2, "max_tokens": 500},
        "generation": {"temperature": 0.5, "max_tokens": 1500},
        "recipe": {"temperature": 0.4, "max_tokens": 3000},
        "freestyle": {"temperature": 0.6, "max_tokens": 2000}
    }
    
    @staticmethod
    def _sanitize_input(text: str, max_length: int = 500) -> str:
        if not text:
            return ""
        sanitized = text.strip()
        sanitized = sanitized.replace('"', "'").replace('`', "'")
        sanitized = re.sub(r'[\r\n\t]', ' ', sanitized)
        sanitized = re.sub(r'\s+', ' ', sanitized)
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "..."
        return sanitized
    
    @staticmethod
    async def _send_groq_request(
        system_prompt: str, 
        user_text: str, 
        task_type: str = "generation",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        try:
            config = GroqService.LLM_CONFIG.get(task_type, GroqService.LLM_CONFIG["generation"])
            final_temperature = temperature if temperature is not None else config["temperature"]
            final_max_tokens = max_tokens if max_tokens is not None else config["max_tokens"]
            
            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=final_max_tokens,
                temperature=final_temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API Error: {e}")
            return ""

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.replace("```json", "").replace("```", "")
        start_brace = text.find('{')
        start_bracket = text.find('[')
        if start_brace == -1: start = start_bracket
        elif start_bracket == -1: start = start_brace
        else: start = min(start_brace, start_bracket)
        end_brace = text.rfind('}')
        end_bracket = text.rfind(']')
        end = max(end_brace, end_bracket)
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        return text.strip()

    FLAVOR_RULES = """❗️ ПРАВИЛА СОЧЕТАЕМОСТИ:
🎭 КОНТРАСТЫ: Жирное + Кислое, Сладкое + Солёное, Мягкое + Хрустящее.
✨ УСИЛЕНИЕ: Помидор + Базилик, Рыба + Укроп + Лимон, Тыква + Корица.
👑 ОДИН ГЛАВНЫЙ ИНГРЕДИЕНТ: В каждом блюде один "король".
❌ ТАБУ: Рыба + Молочные продукты (в горячем), два сильных мяса в одной композиции.
"""

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        prompt = """Ты эксперт по безопасности продуктов. Проверь текст на валидность.
📋 КРИТЕРИИ: ✅ ПРИНЯТЬ (еда, специи, опечатки), ❌ ОТКЛОНИТЬ (яд, мат, бред, приветствия, <3 симв).
🎯 СТРОГИЙ JSON: {"valid": true, "reason": "кратко"}"""
        safe_text = GroqService._sanitize_input(text, max_length=200)
        res = await GroqService._send_groq_request(prompt, f'Текст: "{safe_text}"', task_type="validation")
        try:
            data = json.loads(GroqService._extract_json(res))
            return data.get("valid", False)
        except:
            return "true" in res.lower()

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        safe_products = GroqService._sanitize_input(products, max_length=300)

        if ',' not in safe_products and ';' not in safe_products and '\n' not in safe_products:
            items = [i.strip() for i in safe_products.split() if len(i.strip()) > 1]
        else:
            items = [i.strip() for i in re.split(r'[,;\n\.]', safe_products) if len(i.strip()) > 1]

        items_count = len(items)
        mix_available = items_count >= 8

        prompt = f"""Ты шеф-повар. Определи категории блюд.
🛒 ПРОДУКТЫ: {safe_products}
📦 БАЗА (ВСЕГДА В НАЛИЧИИ): соль, сахар, вода, подсолнечное масло, специи.
📊 Кол-во продуктов: {items_count}

📚 КАТЕГОРИИ:
- "mix" (ПОЛНЫЙ ОБЕД) — ОБЯЗАТЕЛЬНО ПЕРВЫМ, если продуктов >= 8.
- "soup", "main", "salad", "breakfast", "dessert", "drink", "snack".

🎯 ТРЕБОВАНИЯ:
1. Если продуктов >= 8, верни "mix" и еще 3 подходящие категории.
2. Если продуктов < 8, верни от 2 до 4 категорий.
🎯 JSON: ["mix", "cat2", "cat3", "cat4"]"""
        
        res = await GroqService._send_groq_request(prompt, "Определи категории", task_type="categorization", temperature=0.1)
        try:
            data = json.loads(GroqService._extract_json(res))
            if isinstance(data, list):
                if mix_available and "mix" not in data:
                    data.insert(0, "mix")
                elif not mix_available and "mix" in data:
                    data = [item for item in data if item != "mix"]
                return data[:4]
        except:
            pass
        return ["mix", "main", "soup", "salad"] if mix_available else ["main", "soup"]

        @staticmethod
    async def generate_dishes_list(products: str, category: str) -> List[Dict[str, str]]:
        safe_products = GroqService._sanitize_input(products, max_length=400)
        base_instruction = "⚠️ ВАЖНО: соль, сахар, вода, масло и специи ДОСТУПНЫ ВСЕГДА."
        
        if category == "mix":
            prompt = f"""📝 ЗАДАНИЕ: Составь ОДИН комплексный обед из 4-х блюд.
🛒 ПРОДУКТЫ: {safe_products}
📦 БАЗА: соль, сахар, вода, масло, специи.
{base_instruction}

🎯 ТРЕБОВАНИЯ К ФОРМАТУ ПОЛЕЙ:
- Поле "name": СТРОГО одно из названий: "Суп", "Второе блюдо", "Салат" или "Напиток" (на языке ввода, если это не русский, но сохрани структуру).
- Поле "desc": Краткое аппетитное описание блюда на РУССКОМ языке.

🎯 ТРЕБОВАНИЯ К МЕНЮ:
- СТРОГО 4 блюда в списке.
- Распредели продукты логично: основной белок в суп и второе, овощи в салат, ягоды/фрукты в напиток.
🎯 JSON: [
  {{ "name": "Суп", "desc": "Описание..." }},
  {{ "name": "Второе блюдо", "desc": "Описание..." }},
  {{ "name": "Салат", "desc": "Описание..." }},
  {{ "name": "Напиток", "desc": "Описание..." }}
]"""
        else:
            prompt = f"""📝 ЗАДАНИЕ: Составь меню "{category}".
🛒 ПРОДУКТЫ: {safe_products}
{base_instruction}
🎯 ТРЕБОВАНИЯ К ЯЗЫКУ:
- Поле "name": Название блюда на языке ввода.
- Поле "desc": Описание на РУССКОМ языке.
🎯 JSON: [{{ "name": "...", "desc": "..." }}]"""
        
        res = await GroqService._send_groq_request(prompt, "Генерируй меню", task_type="generation")
        try:
            return json.loads(GroqService._extract_json(res))
        except:
            return []


    @staticmethod
    async def generate_recipe(dish_name: str, products: str) -> str:
        safe_dish_name = GroqService._sanitize_input(dish_name, max_length=150)
        safe_products = GroqService._sanitize_input(products, max_length=600)
        is_mix = "полный обед" in safe_dish_name.lower() or "+" in safe_dish_name
        base_rules = "⚠️ БАЗА (ДОСТУПНА ВСЕГДА): соль, сахар, вода, подсолнечное масло, специи."
        
        is_russian_input = bool(re.search('[а-яА-Я]', safe_products))

        if is_mix:
            instruction = "🍱 ПОЛНЫЙ ОБЕД ИЗ 4 БЛЮД. Раздели на блоки: [СУП], [ВТОРОЕ], [САЛАТ], [НАПИТОК]."
        else:
            instruction = "Напиши рецепт одного блюда."

        if is_russian_input:
            translation_rule = "Пиши названия ингредиентов СТРОГО на русском языке без скобок и повторений."
        else:
            translation_rule = "Заголовок и ингредиенты: на языке оригинала. В скобках рядом напиши перевод на РУССКИЙ (напр. 'Pollo (курица)')."

        prompt = f"""Ты профессиональный шеф. Напиши рецепт: "{safe_dish_name}".
🛒 ПРОДУКТЫ: {safe_products}
{base_rules}

🎯 ТРЕБОВАНИЯ К ЯЗЫКУ:
1. {translation_rule}
2. Шаги приготовления и Совет: Пиши СТРОГО на РУССКОМ языке.

{instruction}
{GroqService.FLAVOR_RULES}

📋 СТРОГИЙ ФОРМАТ:
{safe_dish_name}
📦 Ингредиенты:
- [Название] — [количество]

📊 Пищевая ценность на 1 порцию:
🥚 Белки: X г | 🥑 Жиры: X г | 🌾 Углеводы: X г | ⚡ Энерг. ценность: X ккал

⏱ Время: X минут | 🪦 Сложность: [низкая/средняя/высокая] | 👥 Порции: X человека

👨‍🍳 Приготовление:
1. [шаг на русском]

💡 СОВЕТ ШЕФ-ПОВАРА: Напиши СТРОГО на русском языке. Проанализируй блюдо через триаду: ВКУС, АРОМАТ, ТЕКСТУРА.
Порекомендуй ровно один ингредиент, которого нет в списке, для улучшения этой триады.
"""
        res = await GroqService._send_groq_request(prompt, "Напиши рецепт", task_type="recipe")
        if GroqService._is_refusal(res):
            return res
        return res + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str) -> str:
        safe_dish_name = GroqService._sanitize_input(dish_name, max_length=100)
        
        is_russian_input = bool(re.search('[а-яА-Я]', safe_dish_name))
        
        if is_russian_input:
            translation_rule = "Пиши названия ингредиентов СТРОГО на русском языке без скобок и повторений."
        else:
            translation_rule = "Название и ингредиенты — на языке оригинала, перевод на русский в скобках."

        prompt = f"""Ты креативный шеф-повар. Рецепт: "{safe_dish_name}"
🎯 ТРЕБОВАНИЯ К ЯЗЫКУ:
1. {translation_rule}
2. Шаги приготовления и Совет: Пиши СТРОГО на РУССКОМ языке.

📋 СТРОГИЙ ФОРМАТ (СОБЛЮДАЙ ЭМОДЗИ):
{safe_dish_name}
📦 Ингредиенты: ...
📊 Пищевая ценность на 1 порцию: 🥚 Белки: X г | 🥑 Жиры: X г | 🌾 Углеводы: X г | ⚡ Энерг. ценность: X ккал
⏱ Время: X минут | 🪦 Сложность: ... | 👥 Порции: ...
👨‍🍳 Приготовление: ...
💡 СОВЕТ ШЕФА: [анализ вкуса/аромата/текстуры на русском]"""

        res = await GroqService._send_groq_request(prompt, "Создай рецепт", task_type="freestyle")
        if GroqService._is_refusal(res):
            return res
        return res + "\n\n👨‍🍳 <b>Приятного аппетита!</b>"

    @staticmethod
    def _is_refusal(text: str) -> bool:
        refusals = ["cannot fulfill", "against my policy", "не могу выполнить", "⛔"]
        return any(ph in text.lower() for ph in refusals)