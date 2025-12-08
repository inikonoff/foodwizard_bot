from typing import Dict, List, Optional
from config import MAX_HISTORY_MESSAGES

class StateManager:
    """Управление состоянием пользователей"""
    
    def __init__(self):
        # Словарь для хранения истории: {user_id: [messages]}
        self.user_history: Dict[int, List[Dict]] = {}
    
    def add_message(self, user_id: int, role: str, text: str):
        """Добавляет сообщение в историю пользователя"""
        if user_id not in self.user_history:
            self.user_history[user_id] = []
        
        self.user_history[user_id].append({
            "role": role,
            "text": text
        })
        
        # Ограничиваем размер истории
        if len(self.user_history[user_id]) > MAX_HISTORY_MESSAGES:
            self.user_history[user_id] = self.user_history[user_id][-MAX_HISTORY_MESSAGES:]
    
    def get_history(self, user_id: int) -> List[Dict]:
        """Получает историю пользователя"""
        return self.user_history.get(user_id, [])
    
    def get_last_bot_message(self, user_id: int) -> Optional[str]:
        """Получает последнее сообщение бота"""
        history = self.get_history(user_id)
        for msg in reversed(history):
            if msg["role"] == "bot":
                return msg["text"]
        return None
    
    def get_products(self, user_id: int) -> Optional[str]:
        """Извлекает список продуктов из первого сообщения пользователя"""
        history = self.get_history(user_id)
        for msg in history:
            if msg["role"] == "user":
                return msg["text"]
        return None
    
    def update_products(self, user_id: int, additional_products: str):
        """Добавляет новые продукты к существующим"""
        history = self.get_history(user_id)
        
        # Ищем первое сообщение пользователя с продуктами
        for msg in history:
            if msg["role"] == "user":
                msg["text"] = f"{msg['text']}, {additional_products}"
                break
    
    def clear_history(self, user_id: int):
        """Очищает историю пользователя"""
        if user_id in self.user_history:
            del self.user_history[user_id]
    
    def get_context_for_groq(self, user_id: int) -> str:
        """Формирует контекст для передачи в Groq"""
        history = self.get_history(user_id)
        
        context_parts = []
        for msg in history:
            role_label = "Пользователь" if msg["role"] == "user" else "Бот"
            context_parts.append(f"{role_label}: {msg['text']}")
        
        return "\n\n".join(context_parts)

# Глобальный экземпляр менеджера состояний
state_manager = StateManager()