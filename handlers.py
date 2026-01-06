[file name]: handlers.py (обновленные импорты и изменения)
[file content begin]
import os
import io
import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import VoiceProcessor
from groq_service import GroqService
from state_manager_db import state_manager  # Импортируем НОВЫЙ state_manager
from database import db  # Импортируем для сохранения рецептов

# Инициализация
voice_processor = VoiceProcessor()
groq_service = GroqService()
logger = logging.getLogger(__name__)

# --- Остальной код handlers.py остается БЕЗ ИЗМЕНЕНИЙ ---
# (только везде где был state_manager - теперь он с БД)
[file content end]
