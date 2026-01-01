import os
import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import VoiceProcessor
from groq_service import GroqService
from state_manager import state_manager

voice_processor = VoiceProcessor()
logger = logging.getLogger(__name__)

CATEGORY_MAP = {
    "breakfast": "🍳 Завтраки", "soup": "🍲 Супы", "main": "🍝 Вторые блюда",
    "salad": "🥗 Салаты", "snack": "🥪 Закуски", "dessert": "🍰 Десерты", "drink": "🥤 Напитки"
}

# --- КЛАВИАТУРЫ ---
def get_categories_keyboard(categories: list):
    builder = []
    row = []
    for cat_key in categories:
        text = CATEGORY_MAP.get(cat_key, cat_key.capitalize())
        row.append(InlineKeyboardButton(text=text, callback_data=f"cat_{cat_key}"))
        if len(row) == 2:
            builder.append(row); row = []
    if row: builder.append(row)
    builder.append([InlineKeyboardButton(text="🗑 Сброс", callback_data="restart")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_dishes_keyboard(dishes_list: list):
    # Используем display_name для кнопок, чтобы был виден перевод
    builder = [[InlineKeyboardButton(text=d.get('display_name', d['name'])[:40], callback_data=f"dish_{i}")] 
               for i, d in enumerate(dishes_list)]
    builder.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_recipe_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другой вариант", callback_data="repeat_recipe")],
        [InlineKeyboardButton(text="⬅️ К категориям", callback_data="back_to_categories")]
    ])

# --- ЛОГИКА ---
async def cmd_start(message: Message):
    state_manager.clear_session(message.from_user.id)
    # ИСПРАВЛЕНИЕ 1: Использование метода get_welcome_message
    text = GroqService.get_welcome_message()
    await message.answer(text, parse_mode="HTML")

async def handle_text(message: Message):
    user_id = message.from_user.id
    intent_data = await GroqService.determine_intent(message.text)
    
    if intent_data.get("intent") == "recipe":
        await generate_and_send_recipe(message, user_id, intent_data.get("dish", message.text))
    else:
        if not state_manager.get_products(user_id):
            if not await GroqService.validate_ingredients(message.text):
                return await message.answer("🧐 Это не похоже на еду. Попробуйте еще раз.")
            state_manager.set_products(user_id, message.text)
        else:
            state_manager.append_products(user_id, message.text)
        
        products = state_manager.get_products(user_id)
        wait = await message.answer("👨‍🍳 Анализирую...")
        categories = await GroqService.analyze_categories(products)
        state_manager.set_categories(user_id, categories)
        await wait.delete()
        await message.answer(f"✅ У нас есть: <i>{products}</i>\nЧто приготовим?", 
                             reply_markup=get_categories_keyboard(categories), parse_mode="HTML")

async def generate_and_send_recipe(message: Message, user_id: int, dish_name: str):
    wait = await message.answer(f"👨‍🍳 Готовлю рецепт: <b>{dish_name}</b>...", parse_mode="HTML")
    products = state_manager.get_products(user_id) or "базовый набор"
    recipe = await GroqService.generate_recipe(dish_name, products)
    await wait.delete()
    state_manager.set_current_dish(user_id, dish_name)
    # ИСПРАВЛЕНИЕ 2 & 4: Название и структура уже внутри метода generate_recipe
    await message.answer(recipe, reply_markup=get_recipe_back_keyboard(), parse_mode="HTML")

async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if data.startswith("cat_"):
        cat_key = data.split("_")[1]
        # ИСПРАВЛЕНИЕ 3а: Динамическое название категории вместо "Меню"
        category_title = CATEGORY_MAP.get(cat_key, "Блюда")
        
        products = state_manager.get_products(user_id)
        dishes = await GroqService.generate_dishes_list(products, cat_key)
        state_manager.set_generated_dishes(user_id, dishes)
        
        # ИСПРАВЛЕНИЕ 3б: Формируем текстовое описание со списком блюд
        menu_text = f"🍽 <b>{category_title}</b>\n\n"
        for d in dishes:
            menu_text += f"🔸 <b>{d['display_name']}</b>\n{d['desc']}\n\n"
        
        await callback.message.edit_text(menu_text, reply_markup=get_dishes_keyboard(dishes), parse_mode="HTML")
    
    elif data.startswith("dish_"):
        index = int(data.split("_")[1])
        dish_name = state_manager.get_generated_dish(user_id, index)
        await callback.message.delete()
        await generate_and_send_recipe(callback.message, user_id, dish_name)
        
    elif data == "restart":
        state_manager.clear_session(user_id)
        text = GroqService.get_welcome_message()
        await callback.message.answer(text, parse_mode="HTML")
        
    await callback.answer()

def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_text, F.text)
    dp.callback_query.register(handle_callback)