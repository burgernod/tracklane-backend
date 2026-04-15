import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Получаем ссылку на БД из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")

# Проверка, чтобы сервер сразу сказал, если мы забыли добавить ссылку в Render
if not DATABASE_URL:
    raise ValueError("ОШИБКА: DATABASE_URL не найдена. Пожалуйста, добавьте её в настройки Render (Environment).")

# Подключение к БД Neon.tech
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