import os
from dotenv import load_dotenv

load_dotenv()

# API ключи
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

# Настройки
SPEECH_LANGUAGE = "ru-RU"

# ОБНОВЛЕННАЯ МОДЕЛЬ (Llama 3.3)
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_MAX_TOKENS = 2000

# Папки
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

MAX_HISTORY_MESSAGES = 4

# --- НАСТРОЙКИ КОМПЛЕКСНЫХ ОБЕДОВ ---
ENABLE_COMPLEX_MEALS = True
COMPLEX_MEAL_MIN_INGREDIENTS = 3
COMPLEX_MEAL_MAX_COURSES = 4
COMPLEX_MEAL_EMOJIS = {
    "simple": "🍽️",      # 2 блюда
    "standard": "🍽️✨",  # 3 блюда
    "full": "🍽️🌟"       # 4 блюда
}