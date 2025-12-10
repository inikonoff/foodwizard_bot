from config import MAX_HISTORY_MESSAGES
from typing import Dict, List, Optional

class StateManager:
    def __init__(self):
        self.history: Dict[int, List[dict]] = {}
        self.products: Dict[int, str] = {}
        self.user_states: Dict[int, str] = {}
        
        # Данные текущей сессии (НОВЫЕ ПОЛЯ)
        self.generated_dishes: Dict[int, List[dict]] = {} # Список блюд (для кнопок)
        self.available_categories: Dict[int, List[str]] = {} # Доступные категории
        self.current_dish: Dict[int, str] = {} # Последнее выбранное блюдо

    # --- ИСТОРИЯ ---
    def get_history(self, user_id: int) -> List[dict]:
        return self.history.get(user_id, [])

    def add_message(self, user_id: int, role: str, text: str):
        if user_id not in self.history:
            self.history[user_id] = []
        self.history[user_id].append({"role": role, "text": text})
        if len(self.history[user_id]) > MAX_HISTORY_MESSAGES:
            self.history[user_id] = self.history[user_id][-MAX_HISTORY_MESSAGES:]

    def get_last_bot_message(self, user_id: int) -> Optional[str]:
        hist = self.get_history(user_id)
        for msg in reversed(hist):
            if msg["role"] == "bot":
                return msg["text"]
        return None

    # --- ПРОДУКТЫ ---
    def set_products(self, user_id: int, products: str):
        self.products[user_id] = products

    def get_products(self, user_id: int) -> Optional[str]:
        return self.products.get(user_id)

    def append_products(self, user_id: int, new_products: str):
        current = self.products.get(user_id)
        if current:
            self.products[user_id] = f"{current}, {new_products}"
        else:
            self.products[user_id] = new_products

    # --- СТАТУСЫ ---
    def set_state(self, user_id: int, state: str):
        self.user_states[user_id] = state

    def get_state(self, user_id: int) -> Optional[str]:
        return self.user_states.get(user_id)

    def clear_state(self, user_id: int):
        if user_id in self.user_states:
            del self.user_states[user_id]

    # --- НОВОЕ: КАТЕГОРИИ И БЛЮДА ---
    def set_categories(self, user_id: int, categories: List[str]):
        self.available_categories[user_id] = categories

    def get_categories(self, user_id: int) -> List[str]:
        return self.available_categories.get(user_id, [])

    def set_generated_dishes(self, user_id: int, dishes: List[dict]):
        self.generated_dishes[user_id] = dishes

    def get_generated_dish(self, user_id: int, index: int) -> Optional[str]:
        dishes = self.generated_dishes.get(user_id, [])
        if 0 <= index < len(dishes):
            return dishes[index]['name']
        return None

    def set_current_dish(self, user_id: int, dish_name: str):
        self.current_dish[user_id] = dish_name

    def get_current_dish(self, user_id: int) -> Optional[str]:
        return self.current_dish.get(user_id)

    # --- ОЧИСТКА (ВОТ ЭТОГО МЕТОДА НЕ ХВАТАЛО) ---
    def clear_session(self, user_id: int):
        if user_id in self.history: del self.history[user_id]
        if user_id in self.products: del self.products[user_id]
        if user_id in self.user_states: del self.user_states[user_id]
        if user_id in self.generated_dishes: del self.generated_dishes[user_id]
        if user_id in self.available_categories: del self.available_categories[user_id]
        if user_id in self.current_dish: del self.current_dish[user_id]

state_manager = StateManager()
