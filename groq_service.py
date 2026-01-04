from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL
from typing import Dict, List
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
            logger.error(f"Kitchen Order Error: {e}")
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

    # --- THE GOLDEN RATIO OF FLAVOR (Kitchen Manifesto) ---
    FLAVOR_RULES = """
    🍽 THE ART OF PLATING & TASTE:
    
    🎭 CONTRAST (The Soul of the Dish):
    • Fat + Acid (Pork + Sauerkraut)
    • Sweet + Salty (Watermelon + Feta)
    • Soft + Crunchy (Cream soup + Croutons)

    ✨ SYNERGY (Flavor Boosting):
    • Tomato + Basil
    • Fish + Dill + Lemon
    • Pumpkin + Cinnamon

    👑 THE PROTAGONIST:
    One "King" ingredient per dish, others are "The Court".

    ✅ CHEF'S CLASSICS:
    • Tomato + Basil + Garlic
    • Lamb + Rosemary/Mint
    • Cheese + Nuts/Honey

    ❌ CULINARY TABOOS:
    • Fish 🐟 + Dairy 🥛 (in hot entrees)
    • Heavy Protein Overload 🥩+🍗 in one composition
    """

    @staticmethod
    async def validate_ingredients(text: str) -> bool:
        prompt = """You are the Head of Food Quality Control. Audit the incoming delivery list for freshness and safety.

📋 INSPECTION CRITERIA:
✅ ACCEPT (Fresh Delivery) if:
- Edible products (meats, veggies, grains, dairy, etc.)
- Minor typos allowed ("patato", "milkk")
- General culinary categories ("herbs", "spices")

❌ REJECT (Hazardous/Spoiled) if:
- Inedible items (gasoline, glass, chemicals)
- Foul language, kitchen slurs, or toxicity
- Gibberish ("asdfgh", "blablabla")
- Greeting-only inputs ("hi", "yo")
- Empty crates or <3 characters

🎯 REPORT FORMAT (STRICT JSON):
{"valid": true, "reason": "short inspection note"}
OR
{"valid": false, "reason": "short rejection note"}

🚨 CRITICAL:
Response must start with "{" and end with "}". No small talk, no markdown.
"""
        res = await GroqService._send_groq_request(prompt, f'📝 Batch to inspect: "{text}"', 0.1)
        try:
            clean_json = GroqService._extract_json(res)
            data = json.loads(clean_json)
            return data.get("valid", False)
        except:
            return "true" in res.lower()

    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        items_count = len(re.split(r'[,;]', products))
        
        # Logic for the "Chef's Tasting Menu" (Mix)
        if items_count >= 8: mix_rule = '- "mix" (Full Course: Soup + Main + Drink/Salad)'
        elif items_count >= 5: mix_rule = '- "mix" (Light Pairing: 2 matching courses)'
        else: mix_rule = '⚠️ "mix" is NOT AVAILABLE (insufficient ingredients)'
        
        prompt = f"""You are a Menu Architect. Categorize the available pantry items into realistic sections.

🛒 CURRENT PANTRY: {products}
📦 STAPLES (Always in stock): salt, sugar, water, oil, spices, ice

📚 SECTIONS:
- "soup", "main", "salad", "breakfast", "dessert", "drink", "snack"
{mix_rule}

⚠️ KITCHEN POLICIES:
1. Return 2-4 most logical sections.
2. Don't overreach — only what's possible with current stock.

🎯 FORMAT: ["section1", "section2"] (JSON ONLY)
"""
        res = await GroqService._send_groq_request(prompt, "Organize the pantry", 0.2)
        try:
            data = json.loads(GroqService._extract_json(res))
            return data if isinstance(data, list) else ["main"]
        except:
            return ["main"]

    @staticmethod
    async def generate_dishes_list(products: str, category: str) -> List[Dict[str, str]]:
        items_count = len(re.split(r'[,]', products))
        target_count = 5 if items_count < 7 else 7

        prompt = f"""You are the Sous-Chef designing today's Specials for the "{category}" section.

🛒 INGREDIENTS: {products}
📦 STAPLES: salt, sugar, water, oil, spices

{GroqService.FLAVOR_RULES}

🎯 TASK:
- Generate EXACTLY {target_count} appetizing dishes.
- Use only pantry items + staples.
- Names should sound like a Michelin-star menu.
- Descriptions (1-2 sentences) should make the guest hungry.

🎯 FORMAT: [{"name": "Dish Name", "desc": "Sensory description"}] (JSON ONLY)
"""
        res = await GroqService._send_groq_request(prompt, "Draft the menu", 0.5)
        try:
            return json.loads(GroqService._extract_json(res))
        except:
            return []

    @staticmethod
    async def generate_recipe(dish_name: str, products: str) -> str:
        prompt = f"""You are the Executive Chef. Write a technical recipe card for: "{dish_name}".

🛒 PANTRY: {products}
📦 STAPLES: salt, sugar, water, oil, spices

{GroqService.FLAVOR_RULES}

📋 RECIPE CARD FORMAT:

[Dish Title]

📦 Mise en Place (Ingredients):
- [item] — [quantity]

📊 Nutritional Balance (Per serving):
🥚 Protein: Xg | 🥑 Fat: Xg | 🌾 Carbs: Xg | ⚡ Energy: X kcal

⏱ Prep & Cook Time: X mins
🎚 Difficulty: [Easy/Medium/Hard]
👥 Yield: X servings

👨‍🍳 Execution:
1. [Step-by-step instructions with professional techniques]

💡 CHEF'S SECRET: [Analyze Taste, Aroma and Texture. Recommend ONE missing item for the perfect balance].
"""
        res = await GroqService._send_groq_request(prompt, "Start cooking", 0.4, max_tokens=2500)
        return res + "\n\n👨‍🍳 <b>Bon Appétit!</b>" if not GroqService._is_refusal(res) else res

    @staticmethod
    async def generate_freestyle_recipe(dish_name: str) -> str:
        prompt = f"""You are a Culinary Philosopher. Create a recipe for: "{dish_name}"

🔍 ANALYSIS:
If it's EDIBLE (Pizza, Pasta) → Standard technical recipe.
If it's METAPHORICAL (Happiness, Success) → An allegorical recipe for the soul.

📋 FORMAT FOR FOOD: [Standard Recipe Card]
📋 FORMAT FOR METAPHOR:
🎭 The Recipe for "{dish_name}"
📦 Ingredients: [Symbolic concepts, e.g., "3 cups of patience"]
👨‍🍳 Preparation: [Wise life advice using culinary terms]
💡 THE SECRET INGREDIENT: [One core philosophical thought]
"""
        res = await GroqService._send_groq_request(prompt, "Compose the creation", 0.6, max_tokens=2000)
        return res + "\n\n👨‍🍳 <b>Enjoy your meal!</b>" if not GroqService._is_refusal(res) else res

    @staticmethod
    def _is_refusal(text: str) -> bool:
        refusals = ["cannot fulfill", "against policy", "kitchen closed", "не могу"]
        return any(ph in text.lower() for ph in refusals) or "⛔" in text