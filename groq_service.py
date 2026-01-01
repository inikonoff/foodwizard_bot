    @staticmethod
    async def analyze_categories(products: str) -> List[str]:
        """
        Определяет категории блюд. 
        Добавлена логика 'виртуальной воды' для активации категории супов.
        """
        prompt = (
            "You are a culinary analyst. Analyze the ingredients. "
            "IMPORTANT: Always assume the user has BASIC products (water, salt, oil, sugar, pepper).\n"
            "If the ingredients allow for making a liquid dish (soup/broth) using water, ALWAYS include 'soup' in the list.\n"
            "Possible keys: ['soup', 'main', 'salad', 'breakfast', 'dessert', 'drink', 'snack'].\n"
            "Return ONLY a JSON array of applicable keys. If very few ingredients, return only the most suitable one."
        )
        res = await GroqService._send_groq_request(prompt, products, 0.2)
        try:
            # Ищем JSON массив в ответе
            clean_json = re.search(r'\[.*\]', res, re.DOTALL).group()
            return json.loads(clean_json)
        except:
            return ["main"]