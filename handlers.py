import os
import io
import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import VoiceProcessor
from groq_service import GroqService
from state_manager import state_manager

# Инициализация
voice_processor = VoiceProcessor()
groq_service = GroqService()
logger = logging.getLogger(__name__)

# --- СЛОВАРЬ КАТЕГОРИЙ ---
CATEGORY_MAP = {
    "breakfast": "🍳 Завтраки",
    "soup": "🍲 Супы",
    "main": "🍝 Вторые блюда",
    "salad": "🥗 Салаты",
    "snack": "🥪 Закуски",
    "dessert": "🍰 Десерты",
    "drink": "🥤 Напитки",
    "sauce": "🍾 Соусы",
    "mix": "🍱 Комплексный обед",
}

# --- КЛАВИАТУРЫ ---

def get_confirmation_keyboard():
    """Кнопки после ввода продуктов: Добавить еще или Готовить"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить продукты", callback_data="action_add_more")],
        [InlineKeyboardButton(text="👨‍🍳 Готовить (Категории)", callback_data="action_cook")]
    ])

def get_categories_keyboard(categories: list):
    builder = []
    row = []
    for cat_key in categories:
        text = CATEGORY_MAP.get(cat_key, cat_key.capitalize())
        row.append(InlineKeyboardButton(text=text, callback_data=f"cat_{cat_key}"))
        if len(row) == 2:
            builder.append(row)
            row = []
    if row: builder.append(row)
    builder.append([InlineKeyboardButton(text="🗑 Сброс", callback_data="restart")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_dishes_keyboard(dishes_list: list):
    builder = []
    for i, dish in enumerate(dishes_list):
        btn_text = f"{dish['name'][:40]}"
        builder.append([InlineKeyboardButton(text=btn_text, callback_data=f"dish_{i}")])
    builder.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_recipe_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другой вариант", callback_data="repeat_recipe")],
        [InlineKeyboardButton(text="⬅️ Вернуться к категориям", callback_data="back_to_categories")]
    ])

def get_hide_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Скрыть", callback_data="delete_msg")]])

# --- ХЭНДЛЕРЫ ---

async def cmd_start(message: Message):
    state_manager.clear_session(message.from_user.id)
    text = (
        "👋 Здравствуйте.\n\n"
        "🎤 <b>Назовите</b> (голосом или текстом) продукты, которые у вас есть.\n"
        "Я предложу рецепты с учетом КБЖУ и кулинарной триады."
    )
    await message.answer(text, parse_mode="HTML")

async def cmd_author(message: Message):
    await message.answer("👨‍💻 Автор бота: @inikonoff")

# Обработка прямого запроса "Дай рецепт ..."
async def handle_direct_recipe(message: Message):
    user_id = message.from_user.id
    dish_name = message.text.lower().replace("дай рецепт", "", 1).strip()
    if len(dish_name) < 3:
        await message.answer("Напишите название блюда.", parse_mode="HTML")
        return

    wait = await message.answer(f"⚡️ Ищу: <b>{dish_name}</b>...", parse_mode="HTML")
    try:
        recipe = await groq_service.generate_freestyle_recipe(dish_name)
        await wait.delete()
        state_manager.set_current_dish(user_id, dish_name)
        state_manager.set_state(user_id, "recipe_sent")
        await message.answer(recipe, reply_markup=get_hide_keyboard(), parse_mode="HTML")
    except Exception:
        await wait.delete()
        await message.answer("Ошибка генерации.")

async def handle_delete_msg(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

async def handle_voice(message: Message):
    user_id = message.from_user.id
    processing_msg = await message.answer("🎧 Слушаю...")
    temp_file = f"temp/voice_{user_id}_{message.voice.file_id}.ogg"
    
    try:
        await message.bot.download(message.voice, destination=temp_file)
        text = await voice_processor.process_voice(temp_file)
        await processing_msg.delete()
        
        try: await message.delete()
        except: pass
        
        await process_products_input(message, user_id, text)
            
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"😕 Не разобрал: {e}")
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass

async def handle_text(message: Message):
    await process_products_input(message, message.from_user.id, message.text)

# --- ГЛАВНАЯ ЛОГИКА ---
async def process_products_input(message: Message, user_id: int, text: str):
    # Пасхалка
    if text.lower().strip(" .!") in ["спасибо", "спс", "благодарю"]:
        if state_manager.get_state(user_id) == "recipe_sent":
            await message.answer("На здоровье! 👨‍🍳")
            state_manager.clear_state(user_id)
            return

    # Если уже был рецепт - сброс
    if state_manager.get_state(user_id) == "recipe_sent":
        state_manager.clear_session(user_id)

    # Логика накопления продуктов
    current_products = state_manager.get_products(user_id)
    
    if not current_products:
        # Валидация при первом вводе
        is_valid = await groq_service.validate_ingredients(text)
        if not is_valid:
            await message.answer(f"🤨 <b>\"{text}\"</b> — не похоже на продукты.", parse_mode="HTML")
            return
        state_manager.set_products(user_id, text)
        msg_text = f"✅ Принято: <b>{text}</b>"
    else:
        state_manager.append_products(user_id, text)
        all_products = state_manager.get_products(user_id)
        msg_text = f"➕ Добавлено: <b>{text}</b>\n🛒 <b>Всего:</b> {all_products}"

    # СРАЗУ показываем кнопки: Добавить еще или Готовить
    await message.answer(msg_text, reply_markup=get_confirmation_keyboard(), parse_mode="HTML")

# --- ЛОГИКА КАТЕГОРИЙ И БЛЮД ---

async def start_category_flow(message: Message, user_id: int):
    products = state_manager.get_products(user_id)
    if not products:
        await message.answer("Список продуктов пуст. Начните заново /start")
        return

    wait = await message.answer("👨‍🍳 Думаю, что приготовить...")
    
    categories = await groq_service.analyze_categories(products)
    
    await wait.delete()
    if not categories:
        await message.answer("Из этого сложно что-то приготовить.")
        return

    state_manager.set_categories(user_id, categories)

    if len(categories) == 1:
        await show_dishes_for_category(message, user_id, products, categories[0])
    else:
        await message.answer("📂 <b>Выберите категорию:</b>", reply_markup=get_categories_keyboard(categories), parse_mode="HTML")

async def show_dishes_for_category(message: Message, user_id: int, products: str, category: str):
    cat_name = CATEGORY_MAP.get(category, "Блюда")
    wait = await message.answer(f"🍳 Подбираю {cat_name}...")
    
    dishes_list = await groq_service.generate_dishes_list(products, category)
    
    if not dishes_list:
        await wait.delete()
        await message.answer("Не удалось придумать рецепты. Попробуйте другую категорию.")
        return

    state_manager.set_generated_dishes(user_id, dishes_list)
    
    response_text = f"🍽 <b>Меню: {cat_name}</b>\n\n"
    for dish in dishes_list:
        response_text += f"🔸 <b>{dish['name']}</b>\n<i>{dish['desc']}</i>\n\n"
    
    state_manager.add_message(user_id, "bot", response_text)
    
    await wait.delete()
    await message.answer(response_text, reply_markup=get_dishes_keyboard(dishes_list), parse_mode="HTML")

async def generate_and_send_recipe(message: Message, user_id: int, dish_name: str):
    wait = await message.answer(f"👨‍🍳 Пишу рецепт: <b>{dish_name}</b>...", parse_mode="HTML")
    products = state_manager.get_products(user_id)
    
    recipe = await groq_service.generate_recipe(dish_name, products)
    
    await wait.delete()
    state_manager.set_current_dish(user_id, dish_name)
    state_manager.set_state(user_id, "recipe_sent")
    
    await message.answer(recipe, reply_markup=get_recipe_back_keyboard(), parse_mode="HTML")

# --- CALLBACKS ---

async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    # 1. Сброс
    if data == "restart":
        state_manager.clear_session(user_id)
        await callback.message.answer("🗑 Список очищен. Жду продукты.")
        await callback.answer()
        return

    # 2. Выбор: Добавить или Готовить
    if data == "action_add_more":
        await callback.message.answer("✏️ Напишите или продиктуйте, что добавить:")
        await callback.answer()
        return
    
    if data == "action_cook":
        await callback.message.delete()
        await start_category_flow(callback.message, user_id)
        await callback.answer()
        return

    # 3. Выбор категории
    if data.startswith("cat_"):
        category = data.split("_")[1]
        products = state_manager.get_products(user_id)
        await callback.message.delete()
        await show_dishes_for_category(callback.message, user_id, products, category)
        await callback.answer()
        return

    # 4. Назад к категориям
    if data == "back_to_categories":
        categories = state_manager.get_categories(user_id)
        if not categories:
            await callback.answer("Сессия истекла.")
            return
        
        await callback.message.delete()
        if len(categories) == 1:
            await callback.message.answer("Категория была одна.", reply_markup=get_categories_keyboard(categories))
        else:
            await callback.message.answer("📂 <b>Выберите категорию:</b>", reply_markup=get_categories_keyboard(categories), parse_mode="HTML")
        await callback.answer()
        return

    # 5. Выбор блюда
    if data.startswith("dish_"):
        try:
            index = int(data.split("_")[1])
            dish_name = state_manager.get_generated_dish(user_id, index)
            if not dish_name:
                await callback.answer("Меню устарело.")
                return
            await callback.answer("Готовлю...")
            await generate_and_send_recipe(callback.message, user_id, dish_name)
        except Exception as e:
            logger.error(f"Dish error: {e}")
        return

    # 6. Повтор
    if data == "repeat_recipe":
        dish_name = state_manager.get_current_dish(user_id)
        if not dish_name:
            await callback.answer("Нет данных.")
            return
        await callback.answer("Генерирую...")
        await generate_and_send_recipe(callback.message, user_id, dish_name)
        return

def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_author, Command("author"))
    dp.message.register(handle_direct_recipe, F.text.lower().startswith("дай рецепт"))
    dp.message.register(handle_voice, F.voice)
    dp.message.register(handle_text, F.text)
    
    dp.callback_query.register(handle_delete_msg, F.data == "delete_msg")
    dp.callback_query.register(handle_callback)