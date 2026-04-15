import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Получаем ссылку на БД из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")

# Так как мы используем драйвер pg8000, нам нужно слегка поправить стандартную ссылку postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)

# Подключение к БД
# Если ссылки нет (например, забыли добавить), выдаст ошибку, чтобы мы сразу поняли в чем дело
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найдена. Пожалуйста, добавьте её в настройки.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Зависимость для получения сессии БД в маршрутах
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()