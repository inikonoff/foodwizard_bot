import os
from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import VoiceProcessor
from groq_service import GroqService
from state_manager import state_manager

# Инициализация сервисов (ImageService удален полностью)
voice_processor = VoiceProcessor()
groq_service = GroqService()

# --- ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ ---

def get_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Простое / Домашнее", callback_data="style_ordinary"),
            InlineKeyboardButton(text="🌶 Экзотическое", callback_data="style_exotic")
        ]
    ])

def get_restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Заново", callback_data="restart")]
    ])

def get_hide_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Скрыть", callback_data="delete_msg")]
    ])

# --- ХЭНДЛЕРЫ ---

async def cmd_start(message: Message):
    user_id = message.from_user.id
    state_manager.clear_history(user_id)
    state_manager.clear_state(user_id)
    await message.answer(
        "👋 Здравствуйте.\n\n"
        "🎤 <b>Отправьте</b> голосовое или текстовое сообщение с перечнем продуктов, и я подскажу, что из них можно приготовить.\n"
        '📝 Или напишите <b>"Дай рецепт [блюдо]"</b>.',
        parse_mode="HTML"
    )

async def cmd_author(message: Message):
    await message.answer(
        "👨‍💻 <b>Разработчик бота:</b> @inikonoff\n\n"
        "Пишите по вопросам и предложениям!",
        parse_mode="HTML"
    )

async def handle_easter_egg_recipe(message: Message):
    user_id = message.from_user.id
    dish_name = message.text.lower().replace("дай рецепт", "", 1).strip()
    if not dish_name:
        await message.answer("Напиши название блюда. Например: <b>Дай рецепт Пицца</b>")
        return

    wait_msg = await message.answer(f"⚡️ Ищу рецепт: {dish_name}...")
    try:
        recipe = await groq_service.generate_freestyle_recipe(dish_name)
        await wait_msg.delete()
        
        # ИСПРАВЛЕНО: Просто отправляем текст, без проверок несуществующего image_url
        await message.answer(recipe, reply_markup=get_hide_keyboard(), parse_mode="HTML")
        
        state_manager.set_state(user_id, "recipe_sent")
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"Ошибка: {e}")

async def handle_delete_msg(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

# --- ОБРАБОТКА ПРОДУКТОВ ---

async def handle_voice(message: Message):
    user_id = message.from_user.id
    processing_msg = await message.answer("🎧 Слушаю...")
    temp_file = f"temp/voice_{user_id}_{message.voice.file_id}.ogg"
    
    try:
        await message.bot.download(message.voice, destination=temp_file)
        text = await voice_processor.process_voice(temp_file)
        await processing_msg.delete()
        
        history = state_manager.get_history(user_id)
        if not history:
            await handle_initial_products(message, user_id, text)
        else:
            await handle_user_choice(message, user_id, text)
            
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"😕 Не разобрал: {e}")
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass

async def handle_initial_products(message: Message, user_id: int, products: str):
    # 1. ВАЛИДАЦИЯ
    is_valid = await groq_service.validate_ingredients(products)
    
    if not is_valid:
        await message.answer(
            f"🤨 <b>\"{products}\"</b> — это не похоже на список продуктов для готовки.\n\n"
            "Перечислите ингредиенты, например: <i>Курица, картошка, лук</i>.",
            parse_mode="HTML"
        )
        return

    state_manager.add_message(user_id, "user", products)
    state_manager.clear_state(user_id)
    
    await message.answer(
        f"✅ Принято: <
