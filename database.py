from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, BigInteger, Text, Boolean, DateTime, Integer, JSON
from sqlalchemy.sql import func
from sqlalchemy.engine import make_url
from config import DATABASE_URL

Base = declarative_base()

# Модели (остаются прежними)
class User(Base):
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    username = Column(Text)
    full_name = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_premium = Column(Boolean, default=False)
    interaction_count = Column(Integer, default=0)

class UserSession(Base):
    __tablename__ = 'user_sessions'
    user_id = Column(BigInteger, primary_key=True)
    products = Column(Text)
    dialog_history = Column(JSON, default=[])
    state = Column(Text)
    generated_dishes = Column(JSON, default=[])
    available_categories = Column(JSON, default=[])
    current_dish = Column(Text)
    user_lang = Column(Text, default='ru')
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing!")

# Обработка URL для asyncpg
url_obj = make_url(DATABASE_URL)
# Формируем чистый URL без параметров
db_url = f"postgresql+asyncpg://{url_obj.username}:{url_obj.password}@{url_obj.host}:{url_obj.port}/{url_obj.database}"

# Создаем движок с поддержкой SSL (критично для Supabase)
engine = create_async_engine(
    db_url,
    echo=False,
    connect_args={
        "ssl": "require",
        "server_settings": {
            "tcp_user_timeout": "30000" # Защита от зависших соединений
        }
    }
)

async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)