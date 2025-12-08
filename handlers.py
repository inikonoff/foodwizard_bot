import os
from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import VoiceProcessor
from groq_service import GroqService
from image_service import ImageService
from state_manager import state_manager

voice_processor = VoiceProcessor()
groq_service = GroqService()
image_service = ImageService()

async def cmd_start(message: Message):
    user_id = message.from_user.id
    state_manager.clear_history(user_id)
    await message.answer("👋 Привет! Отправь мне голосовое сообщение со списком продуктов.")

async def handle_voice(message: Message):
    user_id = message.from_user.id
    processing_msg = await message.answer("🎧 Слушаю...")
    
    temp_file = f"temp/voice_{user_id}_{message.voice.file_id}.ogg"
    
    try:
        # Скачиваем
        await message.bot.download(message.voice, destination=temp_file)
        
        # Распознаем
        text = await voice_processor.process_voice(temp_file)
        await processing_msg.delete()
        
        # Логика диалога
        history = state_manager.get_history(user_id)
        if not history:
            await handle_initial_products(message, user_id, text)
        else:
            await handle_user_choice(message, user_id, text)
            
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"😕 Не удалось разобрать: {e}")
        # Чистим файл в случае ошибки, если он остался
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass

async def handle_initial_products(message: Message, user_id: int, products: str):
    state_manager.add_message(user_id, "user", products)
    wait_msg = await message.answer("🍳 Придумываю блюда...")
    
    try:
        response = await groq_service.generate_dishes(products)
        state_manager.add_message(user_id, "bot", response)
        await wait_msg.delete()
        await message.answer(response)
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"Ошибка нейросети: {e}")

async def handle_user_choice(message: Message, user_id: int, text: str):
    last_bot_msg = state_manager.get_last_bot_message(user_id)
    if not last_bot_msg:
        await message.answer("История пуста. Нажми /start")
        return

    wait_msg = await message.answer("🤔 Понимаю...")
    try:
        intent = await groq_service.determine_intent(text, last_bot_msg)
        await wait_msg.delete()

        if intent.get("intent") == "select_dish":
            await handle_dish_selection(message, user_id, intent.get("dish_name"))
        elif intent.get("intent") == "add_products":
            await handle_add_products(message, user_id, intent.get("products"))
        else:
            await message.answer("Не совсем понял. Назови блюдо или добавь продукты.")
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
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Заново", callback_data="restart")]])
        
        if image_url:
            await message.answer_photo(image_url, caption=recipe[:1024], reply_markup=kb)
            if len(recipe) > 1024:
                await message.answer(recipe[1024:])
        else:
            await message.answer(recipe, reply_markup=kb)
            
        state_manager.clear_history(user_id)
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"Ошибка рецепта: {e}")

async def handle_add_products(message: Message, user_id: int, new_products: str):
    state_manager.update_products(user_id, new_products)
    all_products = state_manager.get_products(user_id)
    wait_msg = await message.answer("🔄 Обновляю меню...")
    try:
        response = await groq_service.generate_dishes(all_products)
        state_manager.add_message(user_id, "bot", response)
        await wait_msg.delete()
        await message.answer(f"✅ Добавлено: {new_products}\n\n{response}")
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"Ошибка: {e}")

async def handle_restart(callback: CallbackQuery):
    state_manager.clear_history(callback.from_user.id)
    await callback.message.answer("Сброс! Жду список продуктов.")
    await callback.answer()

def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_voice, F.voice)
    dp.callback_query.register(handle_restart, F.data == "restart")