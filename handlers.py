import os
import io
import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import VoiceProcessor
from groq_service import GroqService
from state_manager import state_manager
from database import db as database

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

def get_stats_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить мою историю", callback_data="clear_my_history")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="delete_msg")]
    ])

# --- ХЭНДЛЕРЫ КОМАНД ---

async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # Создаем/получаем пользователя в БД
    try:
        await database.get_or_create_user(
            telegram_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        
        # Пытаемся загрузить предыдущую сессию из БД
        await state_manager.load_user_session(user_id)
        
        # Проверяем, есть ли активная сессия
        current_products = state_manager.get_products(user_id)
        
        if current_products:
            # Продолжаем существующую сессию
            text = (
                "🔄 <b>Продолжаем предыдущую сессию</b>\n\n"
                f"🛒 Ваши продукты: <b>{current_products}</b>\n\n"
                "✏️ Добавьте продукты или выберите:"
            )
            await message.answer(text, reply_markup=get_confirmation_keyboard(), parse_mode="HTML")
        else:
            # Новая сессия
            await state_manager.clear_session(user_id)
            text = (
                "👋 Здравствуйте.\n\n"
                "🎤 Отправьте голосовое или текстовое сообщение с перечнем продуктов на русском или иностранном языке, и я подскажу, что из них можно приготовить.\n"
                "📝 Или напишите 'Дай рецепт [блюдо]'.\n"
            )
            await message.answer(text, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка при старте: {e}")
        # Фолбэк на стандартный старт
        await state_manager.clear_session(user_id)
        text = (
            "👋 Здравствуйте.\н"
            "🎤 Отправьте голосовое или текстовое сообщение с перечнем продуктов, и я подскажу, что из них можно приготовить.\n"
            "📝 Или напишите 'Дай рецепт [блюдо]'.\n"
        )
        await message.answer(text, parse_mode="HTML")

async def cmd_author(message: Message):
    """Показать информацию об авторе"""
    await message.answer("👨‍💻 Автор бота: @inikonoff")

async def cmd_stats(message: Message):
    """Показать статистику бота"""
    try:
        stats = await database.get_stats()
        user_id = message.from_user.id
        
        # Получаем данные пользователя
        user_recipes = await database.get_user_recipes(user_id, limit=5)
        recipes_text = "\n".join([f"• {r['dish_name']} ({r['created_at'].strftime('%d.%m')})" 
                                  for r in user_recipes]) if user_recipes else "Пока нет сохраненных рецептов"
        
        text = (
            "📊 <b>Статистика бота:</b>\n\n"
            f"👤 Всего пользователей: {stats['users']}\n"
            f"📱 Активных сессий: {stats['active_sessions']}\n"
            f"📝 Сохранённых рецептов: {stats['saved_recipes']}\n\n"
            f"<b>Ваши последние рецепты:</b>\n{recipes_text}\n\n"
            "💾 База данных: Supabase"
        )
        await message.answer(text, reply_markup=get_stats_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await message.answer("❌ Ошибка получения статистики")

# --- ФУНКЦИИ ДЛЯ ОПРЕДЕЛЕНИЯ НАМЕРЕНИЯ ---

def is_recipe_request(text: str) -> bool:
    """Определяет, является ли текст запросом на рецепт"""
    if not text:
        return False
    text_lower = text.lower().strip()
    return (text_lower.startswith("дай рецепт") or 
            text_lower.startswith("рецепт") or
            text_lower.startswith("как приготовить") or
            text_lower.startswith("how to cook") or
            text_lower.startswith("recipe for"))

def extract_dish_name_from_request(text: str) -> str:
    """Извлекает название блюда из запроса"""
    text_lower = text.lower().strip()
    
    # Убираем ключевые фразы
    phrases_to_remove = [
        "дай рецепт", "рецепт", "как приготовить", 
        "how to cook", "recipe for", "please", "пожалуйста"
    ]
    
    for phrase in phrases_to_remove:
        if text_lower.startswith(phrase):
            text_lower = text_lower[len(phrase):].strip()
    
    # Убираем знаки препинания в начале
    text_lower = text_lower.lstrip(":,-. ")
    
    return text_lower

# --- ОБРАБОТКА СООБЩЕНИЙ ---

async def handle_direct_recipe(message: Message):
    """Обработка 'Дай рецепт ...' и других запросов рецептов"""
    user_id = message.from_user.id
    dish_name = extract_dish_name_from_request(message.text)
    
    if len(dish_name) < 3:
        await message.answer("Напишите название блюда.", parse_mode="HTML")
        return

    wait = await message.answer(f"⚡️ Ищу: <b>{dish_name}</b>...", parse_mode="HTML")
    try:
        recipe = await groq_service.generate_freestyle_recipe(dish_name)
        await wait.delete()
        
        # Сохраняем состояние
        await state_manager.set_current_dish(user_id, dish_name)
        await state_manager.set_state(user_id, "recipe_sent")
        
        # Сохраняем рецепт в историю БД
        await state_manager.save_recipe_to_history(user_id, dish_name, recipe)
        
        await message.answer(recipe, reply_markup=get_hide_keyboard(), parse_mode="HTML")
    except Exception as e:
        await wait.delete()
        logger.error(f"Ошибка генерации рецепта: {e}")
        await message.answer("❌ Ошибка генерации рецепта.")

async def handle_delete_msg(callback: CallbackQuery):
    """Удалить сообщение"""
    await callback.message.delete()
    await callback.answer()

async def handle_voice(message: Message):
    """Обработка голосового сообщения"""
    user_id = message.from_user.id
    processing_msg = await message.answer("🎧 Слушаю...")
    temp_file = f"temp/voice_{user_id}_{message.voice.file_id}.ogg"
    
    try:
        await message.bot.download(message.voice, destination=temp_file)
        text = await voice_processor.process_voice(temp_file)
        await processing_msg.delete()
        
        # Удаляем голосовое сообщение для чистоты чата
        try: 
            await message.delete()
        except: 
            pass
        
        # Проверяем, не является ли это запросом рецепта
        if is_recipe_request(text):
            await handle_direct_recipe_from_voice(message, text)
        else:
            await process_products_input(message, user_id, text)
            
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"😕 Не разобрал: {e}")
        if os.path.exists(temp_file):
            try: 
                os.remove(temp_file)
            except: 
                pass

async def handle_direct_recipe_from_voice(message: Message, recognized_text: str):
    """Обработка запроса рецепта из голосового сообщения"""
    user_id = message.from_user.id
    dish_name = extract_dish_name_from_request(recognized_text)
    
    if len(dish_name) < 3:
        await message.answer("Название блюда слишком короткое.", parse_mode="HTML")
        return

    wait = await message.answer(f"⚡️ Ищу: <b>{dish_name}</b>...", parse_mode="HTML")
    try:
        recipe = await groq_service.generate_freestyle_recipe(dish_name)
        await wait.delete()
        
        # Сохраняем состояние
        await state_manager.set_current_dish(user_id, dish_name)
        await state_manager.set_state(user_id, "recipe_sent")
        
        # Сохраняем рецепт в историю БД
        await state_manager.save_recipe_to_history(user_id, dish_name, recipe)
        
        await message.answer(recipe, reply_markup=get_hide_keyboard(), parse_mode="HTML")
    except Exception as e:
        await wait.delete()
        logger.error(f"Ошибка генерации рецепта: {e}")
        await message.answer("❌ Ошибка генерации рецепта.")

async def handle_text(message: Message):
    """Обработка текстового сообщения"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Пропускаем команды
    if text.startswith('/'):
        return
    
    # Проверяем, не является ли это запросом рецепта
    if is_recipe_request(text):
        await handle_direct_recipe(message)
        return
    
    await process_products_input(message, user_id, text)

# --- ГЛАВНАЯ ЛОГИКА ОБРАБОТКИ ПРОДУКТОВ ---

async def process_products_input(message: Message, user_id: int, text: str):
    """Основная логика обработки ввода продуктов (ТОЛЬКО для продуктов)"""
    # Сначала проверяем, что это не запрос рецепта (дополнительная защита)
    if is_recipe_request(text):
        await handle_direct_recipe(message)
        return
    
    # Пасхалка
    if text.lower().strip(" .!") in ["спасибо", "спс", "благодарю"]:
        if state_manager.get_state(user_id) == "recipe_sent":
            await message.answer("На здоровье! 👨‍🍳")
            await state_manager.clear_state(user_id)
            return

    # Если уже был рецепт - сброс
    if state_manager.get_state(user_id) == "recipe_sent":
        await state_manager.clear_session(user_id)

    # Логика накопления продуктов
    current_products = state_manager.get_products(user_id)
    
    if not current_products:
        # Валидация при первом вводе
        is_valid = await groq_service.validate_ingredients(text)
        if not is_valid:
            await message.answer(f"🤨 <b>\"{text}\"</b> — не похоже на продукты.", parse_mode="HTML")
            return
        
        await state_manager.set_products(user_id, text)
        msg_text = f"✅ Принято: <b>{text}</b>"
    else:
        await state_manager.append_products(user_id, text)
        all_products = state_manager.get_products(user_id)
        msg_text = f"➕ Добавлено: <b>{text}</b>\n🛒 <b>Всего:</b> {all_products}"

    # Показываем кнопки: Добавить еще или Готовить
    await message.answer(msg_text, reply_markup=get_confirmation_keyboard(), parse_mode="HTML")

# --- ЛОГИКА КАТЕГОРИЙ И БЛЮД ---

async def start_category_flow(message: Message, user_id: int):
    """Начало выбора категории"""
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

    await state_manager.set_categories(user_id, categories)

    if len(categories) == 1:
        await show_dishes_for_category(message, user_id, products, categories[0])
    else:
        await message.answer("📂 <b>Выберите категорию:</b>", 
                           reply_markup=get_categories_keyboard(categories), 
                           parse_mode="HTML")

async def show_dishes_for_category(message: Message, user_id: int, products: str, category: str):
    """Показать блюда выбранной категории"""
    cat_name = CATEGORY_MAP.get(category, "Блюда")
    wait = await message.answer(f"🍳 Подбираю {cat_name}...")
    
    dishes_list = await groq_service.generate_dishes_list(products, category)
    
    if not dishes_list:
        await wait.delete()
        await message.answer("Не удалось придумать рецепты. Попробуйте другую категорию.")
        return

    await state_manager.set_generated_dishes(user_id, dishes_list)
    
    response_text = f"🍽 <b>Меню: {cat_name}</b>\n\n"
    for dish in dishes_list:
        response_text += f"🔸 <b>{dish['name']}</b>\n<i>{dish['desc']}</i>\n\n"
    
    await state_manager.add_message(user_id, "bot", response_text)
    
    await wait.delete()
    
    # Если это комплексный обед, показываем только одну кнопку
    if category == "mix":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Получить рецепты обеда", callback_data="dish_all_mix")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back_to_categories")]
        ])
    else:
        kb = get_dishes_keyboard(dishes_list)
        
    await message.answer(response_text, reply_markup=kb, parse_mode="HTML")

async def generate_and_send_recipe(message: Message, user_id: int, dish_name: str):
    """Генерация и отправка рецепта"""
    wait = await message.answer(f"👨‍🍳 Пишу рецепт: <b>{dish_name}</b>...", parse_mode="HTML")
    products = state_manager.get_products(user_id)
    
    recipe = await groq_service.generate_recipe(dish_name, products)
    
    await wait.delete()
    
    # Сохраняем состояние
    await state_manager.set_current_dish(user_id, dish_name)
    await state_manager.set_state(user_id, "recipe_sent")
    
    # СОХРАНЯЕМ РЕЦЕПТ В БД
    await state_manager.save_recipe_to_history(user_id, dish_name, recipe)
    
    await message.answer(recipe, reply_markup=get_recipe_back_keyboard(), parse_mode="HTML")

# --- CALLBACK ОБРАБОТЧИКИ ---

async def handle_callback(callback: CallbackQuery):
    """Обработка всех callback-запросов"""
    user_id = callback.from_user.id
    data = callback.data
    
    # 1. Сброс
    if data == "restart":
        await state_manager.clear_session(user_id)
        await callback.message.answer("🗑 Список очищен. Жду продукты.")
        await callback.answer()
        return
    
    # 2. Очистка истории пользователя
    if data == "clear_my_history":
        try:
            # Получаем ID пользователя из БД
            async with database.pool.acquire() as conn:
                await conn.execute("DELETE FROM recipes WHERE user_id = $1", user_id)
            await callback.message.edit_text("✅ Ваша история рецептов очищена.")
        except Exception as e:
            logger.error(f"Ошибка очистки истории: {e}")
            await callback.message.edit_text("❌ Ошибка очистки истории.")
        await callback.answer()
        return

    # 3. Выбор: Добавить или Готовить
    if data == "action_add_more":
        await callback.message.answer("✏️ Напишите или продиктуйте, что добавить:")
        await callback.answer()
        return
    
    if data == "action_cook":
        await callback.message.delete()
        await start_category_flow(callback.message, user_id)
        await callback.answer()
        return

    # 4. Выбор категории
    if data.startswith("cat_"):
        category = data.split("_")[1]
        products = state_manager.get_products(user_id)
        await callback.message.delete()
        await show_dishes_for_category(callback.message, user_id, products, category)
        await callback.answer()
        return

    # 5. Назад к категориям
    if data == "back_to_categories":
        categories = state_manager.get_categories(user_id)
        if not categories:
            await callback.answer("Сессия истекла.")
            return
        
        await callback.message.delete()
        if len(categories) == 1:
            await callback.message.answer("Категория была одна.", 
                                        reply_markup=get_categories_keyboard(categories))
        else:
            await callback.message.answer("📂 <b>Выберите категорию:</b>", 
                                        reply_markup=get_categories_keyboard(categories), 
                                        parse_mode="HTML")
        await callback.answer()
        return

    # 6. Выбор блюда
    if data.startswith("dish_"):
        try:
            # Обработка комплексного обеда
            if data == "dish_all_mix":
                dishes = state_manager.get_generated_dishes(user_id)
                dish_name = " + ".join([d['name'] for d in dishes])
            else:
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

    # 7. Повтор рецепта
    if data == "repeat_recipe":
        dish_name = state_manager.get_current_dish(user_id)
        if not dish_name:
            await callback.answer("Нет данных.")
            return
        await callback.answer("Генерирую...")
        await generate_and_send_recipe(callback.message, user_id, dish_name)
        return

    # 8. Удаление сообщения
    if data == "delete_msg":
        await callback.message.delete()
        await callback.answer()
        return

# --- РЕГИСТРАЦИЯ ХЭНДЛЕРОВ (ИСПРАВЛЕННЫЙ ПОРЯДОК) ---

def register_handlers(dp: Dispatcher):
    # Сначала специфичные обработчики команд
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_author, Command("author"))
    dp.message.register(cmd_stats, Command("stats"))
    
    # Затем обработчик запросов рецептов (до общего обработчика текста!)
    dp.message.register(handle_direct_recipe, F.text.lower().startswith("дай рецепт"))
    dp.message.register(handle_direct_recipe, F.text.lower().startswith("рецепт"))
    dp.message.register(handle_direct_recipe, F.text.lower().startswith("как приготовить"))

dp.message.register(handle_voice, F.voice)
dp.message.register(
  