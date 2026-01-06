import asyncpg
from typing import List, Dict, Any, Optional
import json
import logging
from datetime import datetime
from config import DATABASE_URL  # Импортируем из config.py

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Подключение к базе данных Supabase"""
        try:
            self.pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=5,
                statement_cache_size=0,  # КРИТИЧЕСКИ ВАЖНО для Supabase
                command_timeout=60,
                max_inactive_connection_lifetime=300
            )
            await self._check_tables()
            logger.info("✅ Успешное подключение к Supabase PostgreSQL")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    async def close(self):
        """Graceful shutdown пула соединений"""
        if self.pool:
            await self.pool.close()
            logger.info("💤 Соединение с БД закрыто")

    async def _check_tables(self):
        """Проверяем существование таблиц (не создаём автоматически)"""
        async with self.pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public' 
                AND tablename IN ('users', 'sessions', 'recipes')
            """)
            if len(tables) < 3:
                logger.warning("⚠️  Некоторые таблицы отсутствуют. Убедись, что выполнил SQL из шага 2!")
                logger.warning(f"Найдены таблицы: {[t['tablename'] for t in tables]}")

    # ==================== ПОЛЬЗОВАТЕЛИ ====================

    async def get_or_create_user(
        self, 
        telegram_id: int, 
        username: str = None, 
        first_name: str = None, 
        last_name: str = None,
        language: str = 'ru'
    ) -> Dict:
        """Создаём или получаем пользователя"""
        async with self.pool.acquire() as conn:
            # Пробуем найти существующего
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                telegram_id
            )
            
            if not user:
                # Создаём нового
                user = await conn.fetchrow(
                    """
                    INSERT INTO users (id, username, first_name, last_name, language)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING *
                    """,
                    telegram_id, username, first_name, last_name, language
                )
                logger.info(f"👤 Создан новый пользователь: {telegram_id}")
            else:
                # Обновляем активность
                await conn.execute(
                    """
                    UPDATE users 
                    SET last_active = NOW(), 
                        username = COALESCE($2, username)
                    WHERE id = $1
                    """,
                    telegram_id, username
                )
                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE id = $1",
                    telegram_id
                )
            
            return dict(user)

    async def update_user_language(self, telegram_id: int, language: str):
        """Обновляем язык пользователя"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET language = $1 WHERE id = $2",
                language, telegram_id
            )

    # ==================== СЕССИИ ====================

    async def create_or_update_session(
        self,
        telegram_id: int,
        products: Optional[str] = None,
        state: Optional[str] = None,
        categories: Optional[List[str]] = None,
        generated_dishes: Optional[List[Dict]] = None,
        current_dish: Optional[str] = None,
        history: Optional[List[Dict]] = None
    ) -> Dict:
        """Создаёт или обновляет сессию пользователя"""
        async with self.pool.acquire() as conn:
            # Преобразуем Python объекты в JSON
            categories_json = json.dumps(categories) if categories else None
            dishes_json = json.dumps(generated_dishes) if generated_dishes else None
            history_json = json.dumps(history) if history else None

            # Проверяем существующую сессию
            existing = await conn.fetchrow(
                "SELECT id FROM sessions WHERE user_id = $1",
                telegram_id
            )

            if existing:
                # Обновляем существующую
                session = await conn.fetchrow(
                    """
                    UPDATE sessions 
                    SET 
                        products = COALESCE($2, products),
                        state = COALESCE($3, state),
                        categories = COALESCE($4::jsonb, categories),
                        generated_dishes = COALESCE($5::jsonb, generated_dishes),
                        current_dish = COALESCE($6, current_dish),
                        history = COALESCE($7::jsonb, history),
                        updated_at = NOW()
                    WHERE user_id = $1
                    RETURNING *
                    """,
                    telegram_id, products, state, categories_json, 
                    dishes_json, current_dish, history_json
                )
            else:
                # Создаём новую
                session = await conn.fetchrow(
                    """
                    INSERT INTO sessions 
                    (user_id, products, state, categories, generated_dishes, current_dish, history)
                    VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7::jsonb)
                    RETURNING *
                    """,
                    telegram_id, products, state, categories_json, 
                    dishes_json, current_dish, history_json
                )
            
            return dict(session) if session else None

    async def get_session(self, telegram_id: int) -> Optional[Dict]:
        """Получаем текущую сессию пользователя"""
        async with self.pool.acquire() as conn:
            session = await conn.fetchrow(
                """
                SELECT * FROM sessions 
                WHERE user_id = $1
                ORDER BY updated_at DESC 
                LIMIT 1
                """,
                telegram_id
            )
            
            if session:
                # Преобразуем JSON поля обратно в Python объекты
                session_dict = dict(session)
                
                # categories
                if session_dict.get('categories'):
                    try:
                        session_dict['categories'] = json.loads(session_dict['categories'])
                    except:
                        session_dict['categories'] = []
                
                # generated_dishes
                if session_dict.get('generated_dishes'):
                    try:
                        session_dict['generated_dishes'] = json.loads(session_dict['generated_dishes'])
                    except:
                        session_dict['generated_dishes'] = []
                
                # history
                if session_dict.get('history'):
                    try:
                        session_dict['history'] = json.loads(session_dict['history'])
                    except:
                        session_dict['history'] = []
                
                return session_dict
            return None

    async def update_session_state(self, telegram_id: int, state: str):
        """Обновляем только состояние сессии"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET state = $1, updated_at = NOW() WHERE user_id = $2",
                state, telegram_id
            )

    async def update_session_products(self, telegram_id: int, products: str):
        """Обновляем только продукты в сессии"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET products = $1, updated_at = NOW() WHERE user_id = $2",
                products, telegram_id
            )

    async def clear_session(self, telegram_id: int):
        """Очищаем сессию пользователя (мягкое удаление)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sessions 
                SET 
                    products = NULL,
                    state = NULL,
                    categories = '[]'::jsonb,
                    generated_dishes = '[]'::jsonb,
                    current_dish = NULL,
                    history = '[]'::jsonb,
                    updated_at = NOW()
                WHERE user_id = $1
                """,
                telegram_id
            )
            logger.info(f"🧹 Сессия очищена для пользователя {telegram_id}")

    async def delete_session(self, telegram_id: int):
        """Полное удаление сессии"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM sessions WHERE user_id = $1",
                telegram_id
            )

    # ==================== РЕЦЕПТЫ ====================

    async def save_recipe(
        self,
        telegram_id: int,
        dish_name: str,
        recipe_text: str,
        products_used: Optional[str] = None
    ) -> int:
        """Сохраняем рецепт в историю"""
        async with self.pool.acquire() as conn:
            recipe = await conn.fetchrow(
                """
                INSERT INTO recipes (user_id, dish_name, recipe_text, products_used)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                telegram_id, dish_name, recipe_text, products_used
            )
            logger.info(f"📝 Рецепт сохранён: {dish_name} для пользователя {telegram_id}")
            return recipe['id']

    async def get_user_recipes(self, telegram_id: int, limit: int = 10) -> List[Dict]:
        """Получаем историю рецептов пользователя"""
        async with self.pool.acquire() as conn:
            recipes = await conn.fetch(
                """
                SELECT * FROM recipes 
                WHERE user_id = $1 
                ORDER BY created_at DESC 
                LIMIT $2
                """,
                telegram_id, limit
            )
            return [dict(r) for r in recipes]

    # ==================== АДМИНИСТРАТИВНЫЕ ====================

    async def cleanup_old_sessions(self, days_old: int = 7):
        """Удаляем старые сессии"""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM sessions 
                WHERE updated_at < NOW() - INTERVAL '$1 days'
                """,
                days_old
            )
            logger.info(f"🧹 Удалены старые сессии: {result}")

    async def get_stats(self) -> Dict:
        """Статистика базы данных"""
        async with self.pool.acquire() as conn:
            users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            sessions_count = await conn.fetchval("SELECT COUNT(*) FROM sessions")
            recipes_count = await conn.fetchval("SELECT COUNT(*) FROM recipes")
            
            return {
                "users": users_count,
                "active_sessions": sessions_count,
                "saved_recipes": recipes_count
            }

# Глобальный экземпляр для использования
db = Database()
