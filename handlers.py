import os
from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import VoiceProcessor
from groq_service import GroqService
from image_service import ImageService
from state_manager import state_manager

# Инициализация сервисов
voice_processor = VoiceProcessor()
groq_service = GroqService()
image_service = ImageService()

# --- ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ ---

def get_style_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора стиля"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Простое / Домашнее", callback_data="style_ordinary"),
            InlineKeyboardButton(text="🌶 Экзотическое", callback_data="style_exotic")
        ]
    ])

def get_restart_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой рестарта"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сброс", callback_data="restart")]
    ])

def get_hide_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для скрытия рецепта"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Скрыть", callback_data="delete_msg")]
    ])

# --- ХЭНДЛЕРЫ ---

async def cmd_start(message: Message):
    user_id = message.from_user.id
    state_manager.clear_history(user_id)
    await message.answer(
        "👋 Здравствуйте.\n\n"
        "🎤 Отправьте голосовое или текстовое сообщение с перечнем продуктов, и я подскажу, что из них можно приготовить.\n"
        '📝 Или напишите <b>"Дай рецепт [блюдо]"</b>.',
        parse_mode="HTML"
    )

async def cmd_author(message: Message):
    await message.answer(
        "👨‍💻 <b>Разработчик бота:</b> @inikonoff",
        parse_mode="HTML"
    )

async def handle_easter_egg_recipe(message: Message):
    dish_name = message.text.lower().replace("дай рецепт", "", 1).strip()
    if not dish_name:
        await message.answer("Напиши название блюда. Например: <b>Дай рецепт Пицца</b>")
        return

    wait_msg = await message.answer(f"⚡️ Ищу рецепт: {dish_name}...")
    try:
        recipe = await groq_service.generate_freestyle_recipe(dish_name)
        image_url = await image_service.search_dish_image(dish_name)
        await wait_msg.delete()
        
        kb = get_hide_keyboard()

        # ИСПРАВЛЕНИЕ: Отправляем фото и текст раздельно
        if image_url:
            # Сначала фото
            await message.answer_photo(image_url)
        
        # Потом текст (лимит 4096 символов, этого точно хватит)
        await message.answer(recipe, reply_markup=kb)

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
    state_manager.add_message(user_id, "user", products)
    
    await message.answer(
        f"✅ Принято: <b>{products}</b>\n\n"
        "Какое блюдо вы хотите приготовить?",
        reply_markup=get_style_keyboard(),
        parse_mode="HTML"
    )

async def handle_style_selection_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    style_code = callback.data
    style_name = "простой, домашний" if style_code == "style_ordinary" else "экзотический, необычный"
    
    await callback.answer(f"Выбран стиль: {style_name}")
    products = state_manager.get_products(user_id)
    
    if not products:
        await callback.message.answer("Потерял список продуктов 😢 Начните заново /start")
        return

    await callback.message.edit_text(f"🍳 Подбираю {style_name}е рецепты из: {products}...")
    
    try:
        response = await groq_service.generate_dishes(products, style=style_name)
        state_manager.add_message(user_id, "bot", response)
        
        await callback.message.delete()
        await callback.message.answer(response, reply_markup=get_restart_keyboard())
        
    except Exception as e:
        await callback.message.edit_text(f"Ошибка нейросети: {e}")

# --- ВЫБОР БЛЮДА ИЛИ ДОБАВЛЕНИЕ ---

async def handle_user_choice(message: Message, user_id: int = None, text: str = None):
    if user_id is None:
        user_id = message.from_user.id
    if text is None:
        text = message.text

    last_bot_msg = state_manager.get_last_bot_message(user_id)
    
    if not last_bot_msg:
        await handle_initial_products(message, user_id, text)
        return

    wait_msg = await message.answer("🤔 Обрабатываю...")
    try:
        intent = await groq_service.determine_intent(text, last_bot_msg)
        await wait_msg.delete()

        if intent.get("intent") == "select_dish":
            await handle_dish_selection(message, user_id, intent.get("dish_name"))
        elif intent.get("intent") == "add_products":
            await handle_add_products(message, user_id, intent.get("products"))
        else:
            await message.answer("Не понял. Нажми на блюдо или добавь продукты.")
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"Ошибка: {e}")

async def handle_dish_selection(message: Message, user_id: int, dish_name: str):
    wait_msg = await message.answer(f"👨‍🍳 Пишу рецепт: {dish_name}...")
    try:
        products = state_manager.get_products(user_id)
        recipe = await groq_service.generate_recipe(dish_name, products)
        image_url = await image_service.search_dish_image(dish_name)
        
        await wait_msg.delete()
        
        kb = get_restart_keyboard()
        
        # ИСПРАВЛЕНИЕ: Отправляем фото и текст раздельно
        if image_url:
            # Сначала фото
            await message.answer_photo(image_url)
        
        # Потом текст (лимит 4096 символов, этого точно хватит)
        await message.answer(recipe, reply_markup=kb)
        
        state_manager.clear_history(user_id)
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"Ошибка рецепта: {e}")

async def handle_add_products(message: Message, user_id: int, new_products: str):
    state_manager.update_products(user_id, new_products)
    all_products = state_manager.get_products(user_id)
    wait_msg = await message.answer(f"➕ Добавил: {new_products}. Обновляю меню...")
    try:
        response = await groq_service.generate_dishes(all_products, style="с учетом новых продуктов")
        state_manager.add_message(user_id, "bot", response)
        await wait_msg.delete()
        
        await message.answer(response, reply_markup=get_restart_keyboard())
        
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"Ошибка: {e}")

async def handle_restart(callback: CallbackQuery):
    state_manager.clear_history(callback.from_user.id)
    await callback.message.answer("Сброс! Жду список продуктов.")
    await callback.answer()

def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_author, Command("author"))
    
    dp.message.register(handle_easter_egg_recipe, F.text.lower().startswith("дай рецепт"))
    dp.message.register(handle_voice, F.voice)
    dp.message.register(handle_user_choice, F.text)
    
    dp.callback_query.register(handle_restart, F.data == "restart")
    dp.callback_query.register(handle_delete_msg, F.data == "delete_msg")
    dp.callback_query.register(handle_style_selection_callback, F.data.startswith("style_"))
