import asyncpg
from config import DATABASE_URL
from typing import List, Dict, Any, Optional, Union
import json
import logging

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Подключение к базе данных (точно как в генераторе паролей)"""
        try:
            self.pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=5,
                statement_cache_size=0  # КРИТИЧЕСКИ ВАЖНО для Supabase
            )
            await self._create_tables()
            logging.info("✅ Успешное подключение к базе данных")
        except Exception as e:
            logging.error(f"❌ Критическая ошибка подключения к БД: {e}")
            raise e

    async def close(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()
            logging.info("💤 Соединение с БД закрыто")

    async def _create_tables(self):
        """Создание таблиц если они не существуют"""
        async with self.pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    is_premium BOOLEAN DEFAULT FALSE,
                    interaction_count INTEGER DEFAULT 0
                )
            """)

            # Таблица сессий пользователя
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    products TEXT,
                    dialog_history JSONB DEFAULT '[]'::jsonb,
                    state TEXT,
                    generated_dishes JSONB DEFAULT '[]'::jsonb,
                    available_categories JSONB DEFAULT '[]'::jsonb,
                    current_dish TEXT,
                    user_lang TEXT DEFAULT 'ru',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

    # === CRUD операции для users ===
    async def get_or_create_user(self, user_id: int, username: str = None, full_name: str = None):
        """Получить или создать пользователя"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
            if not user:
                user = await conn.fetchrow(
                    """
                    INSERT INTO users (user_id, username, full_name)
                    VALUES ($1, $2, $3)
                    RETURNING *
                    """,
                    user_id, username, full_name
                )
            else:
                # Обновляем username если изменился
                await conn.execute(
                    "UPDATE users SET username = $2 WHERE user_id = $1",
                    user_id, username
                )
            return dict(user) if user else None

    async def update_user_interaction(self, user_id: int):
        """Увеличить счетчик взаимодействий"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET interaction_count = interaction_count + 1 WHERE user_id = $1",
                user_id
            )

    async def set_user_premium(self, user_id: int, is_premium: bool):
        """Установить premium статус"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_premium = $2 WHERE user_id = $1",
                user_id, is_premium
            )

    # === CRUD операции для user_sessions ===
    async def get_user_session(self, user_id: int):
        """Получить сессию пользователя"""
        async with self.pool.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT * FROM user_sessions WHERE user_id = $1",
                user_id
            )
            return dict(session) if session else None

    async def create_or_update_session(self, user_id: int, **kwargs):
        """Создать или обновить сессию пользователя"""
        async with self.pool.acquire() as conn:
            # Проверяем существующую сессию
            existing = await conn.fetchrow(
                "SELECT user_id FROM user_sessions WHERE user_id = $1",
                user_id
            )
            
            if existing:
                # Обновляем существующую
                fields = []
                values = []
                idx = 2
                
                for key, value in kwargs.items():
                    if value is not None:
                        fields.append(f"{key} = ${idx}")
                        values.append(value)
                        idx += 1
                
                if fields:
                    query = f"""
                        UPDATE user_sessions 
                        SET {', '.join(fields)}, updated_at = NOW()
                        WHERE user_id = $1
                    """
                    await conn.execute(query, user_id, *values)
            else:
                # Создаем новую
                fields = ['user_id']
                placeholders = ['$1']
                field_values = [user_id]
                idx = 2
                
                for key, value in kwargs.items():
                    if value is not None:
                        fields.append(key)
                        placeholders.append(f"${idx}")
                        field_values.append(value)
                        idx += 1
                
                query = f"""
                    INSERT INTO user_sessions ({', '.join(fields)})
                    VALUES ({', '.join(placeholders)})
                """
                await conn.execute(query, *field_values)

    async def update_session_field(self, user_id: int, field: str, value: Any):
        """Обновить конкретное поле в сессии"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE user_sessions 
                SET {field} = $2, updated_at = NOW()
                WHERE user_id = $1
                """,
                user_id, value
            )

    async def add_to_dialog_history(self, user_id: int, message: Dict[str, Any]):
        """Добавить сообщение в историю диалога"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_sessions 
                SET dialog_history = COALESCE(dialog_history, '[]'::jsonb) || $2::jsonb,
                    updated_at = NOW()
                WHERE user_id = $1
                """,
                user_id, json.dumps([message])
            )

    async def clear_dialog_history(self, user_id: int):
        """Очистить историю диалога"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_sessions SET dialog_history = '[]'::jsonb WHERE user_id = $1",
                user_id
            )

    async def delete_session(self, user_id: int):
        """Удалить сессию пользователя"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_sessions WHERE user_id = $1",
                user_id
            )

    # === Утилиты ===
    async def health_check(self):
        """Проверка здоровья БД"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
                return True
        except:
            return False

    async def get_stats(self):
        """Получить статистику БД"""
        async with self.pool.acquire() as conn:
            users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            sessions_count = await conn.fetchval("SELECT COUNT(*) FROM user_sessions")
            
            return {
                "users": users_count,
                "active_sessions": sessions_count,
                "database": "healthy"
            }

# Глобальный экземпляр БД
db = Database()