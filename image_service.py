import aiohttp
from config import UNSPLASH_ACCESS_KEY
from typing import Optional

class ImageService:
    @staticmethod
    async def search_dish_image(dish_name: str) -> Optional[str]:
        if not UNSPLASH_ACCESS_KEY:
            return None
        
        url = "https://api.unsplash.com/search/photos"
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        params = {"query": f"{dish_name} food", "per_page": 1, "orientation": "landscape"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("results"):
                            return data["results"][0]["urls"]["regular"]
            return None
        except Exception as e:
            print(f"Ошибка фото: {e}")
            return None