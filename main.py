from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from fastapi.security import OAuth2PasswordBearer
import models
import hashlib
import jwt
import random
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Это создаст таблицы в базе данных, если их там еще нет
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TrackLane API",
    description="Backend for TrackLane Mobile App (РПО Курсовая)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройки для JWT (Секретный ключ)
SECRET_KEY = "tracklane_super_secret_key_rpo_coursework"
ALGORITHM = "HS256"

def create_access_token(data: dict):
    to_encode = data.copy()
    # Токен будет жить 30 дней (для функции "Запомнить меня")
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@app.get("/")
def read_root():
    return {"message": "TrackLane API is running! База данных подключена."}

def send_otp_email(receiver_email: str, otp_code: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
    
    if not sender_email or not sender_password:
        print("ОШИБКА: SMTP настройки не заданы в .env")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "Код подтверждения TrackLane"
    
    body = f"Добро пожаловать в TrackLane!\n\nВаш код подтверждения: {otp_code}\n\nКод действителен 5 минут."
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        # Настройки для Mail.ru (SSL порт 465)
        server = smtplib.SMTP_SSL('smtp.mail.ru', 465)
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"Письмо успешно отправлено на {receiver_email}")
    except Exception as e:
        print(f"Ошибка отправки email: {e}")

from pydantic import BaseModel

class ColumnCreate(BaseModel):
    title: str
    wip_limit: int

class TaskCreate(BaseModel):
    title: str
    column_id: int

# 1. Создание колонки
@app.post("/api/v1/columns/")
def create_column(column: ColumnCreate, db: Session = Depends(get_db)):
    new_column = models.ColumnModel(title=column.title, wip_limit=column.wip_limit)
    db.add(new_column)
    db.commit()
    db.refresh(new_column)
    return new_column

# 2. Создание задачи с проверкой WIP-лимита
@app.post("/api/v1/tasks/")
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    # Находим колонку
    column = db.query(models.ColumnModel).filter(models.ColumnModel.id == task.column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Колонка не найдена")

    # ПРОВЕРКА WIP-ЛИМИТА
    if column.wip_limit > 0:
        current_tasks = db.query(models.Task).filter(models.Task.column_id == task.column_id).count()
        if current_tasks >= column.wip_limit:
            raise HTTPException(
                status_code=400,
                detail=f"WIP_LIMIT_EXCEEDED: В колонке '{column.title}' лимит {column.wip_limit} задач!"
            )

    new_task = models.Task(title=task.title, column_id=task.column_id)
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

# Обновленная фича проверки WIP-лимита с настоящей БД (Раздел 3.4.3)
@app.put("/api/v1/tasks/{task_id}/move")
def move_task(task_id: int, target_column_id: int, db: Session = Depends(get_db)):
    # 1. Находим целевую колонку
    column = db.query(models.ColumnModel).filter(models.ColumnModel.id == target_column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Колонка не найдена")

    # 2. Если wip_limit > 0, проверяем лимит
    if column.wip_limit > 0:
        current_tasks_count = db.query(models.Task).filter(models.Task.column_id == target_column_id).count()
        if current_tasks_count >= column.wip_limit:
            # Возвращаем ошибку для Snap-Back анимации во Frontend
            raise HTTPException(
                status_code=400,
                detail="WIP_LIMIT_EXCEEDED"
            )
            
    # 3. Находим задачу и меняем ей колонку
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
        
    task.column_id = target_column_id
    db.commit()
    
    return {"message": "Задача успешно перемещена"}

# --- СХЕМЫ ДЛЯ АВТОРИЗАЦИИ (Pydantic) ---
class UserRegister(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class OTPVerify(BaseModel):
    email: str
    otp_code: str

# Простая функция для хэширования пароля (чтобы не хранить пароли в открытом виде)
def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# --- МАРШРУТЫ АВТОРИЗАЦИИ ---

@app.post("/api/v1/auth/register")
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(
        (models.User.email == user.email) | (models.User.username == user.username)
    ).first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким Email или Псевдонимом уже существует")

    otp = str(random.randint(100000, 999999))
    expire_time = datetime.utcnow() + timedelta(minutes=5)

    new_user = models.User(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        otp_code=otp,
        otp_expire=expire_time,
        is_active=False # Пользователь не активен, пока не введет код
    )
    db.add(new_user)
    db.commit()
    
    # ОТПРАВЛЯЕМ ПИСЬМО СРАЗУ
    send_otp_email(user.email, otp)
    
    return {
        "message": "Регистрация успешна. Код отправлен на почту.", 
        "dev_otp": otp # Оставляем для тестов, если SMTP упадет
    }

# --- ИСПРАВЛЕННЫЙ МАРШРУТ ВЕРИФИКАЦИИ ---
@app.post("/api/v1/auth/verify-otp")
def verify_otp(data: OTPVerify, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
        
    if user.otp_code != data.otp_code:
        raise HTTPException(status_code=400, detail="Неверный код")
        
    if datetime.utcnow() > user.otp_expire:
        raise HTTPException(status_code=400, detail="Срок действия кода истек")
        
    user.is_active = True # Активируем
    user.otp_code = None
    db.commit()
    
    return {"message": "Email успешно подтвержден! Теперь вы можете войти."}

# --- ИСПРАВЛЕННЫЙ МАРШРУТ ЛОГИНА ---
@app.post("/api/v1/auth/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # ПРОВЕРКА: Активирован ли аккаунт?
    if not db_user.is_active:
        raise HTTPException(status_code=401, detail="Email не подтвержден. Пожалуйста, введите OTP код.")
        
    if db_user.hashed_password != hash_password(user.password):
        raise HTTPException(status_code=400, detail="Неверный пароль")
    
    token = create_access_token({"sub": db_user.username, "role": db_user.role})
        
    return {
        "token": token,
        "username": db_user.username,
        "message": "Успешный вход"
    }

    # --- СХЕМЫ ДЛЯ СБРОСА ПАРОЛЯ ---
class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordConfirm(BaseModel):
    email: str
    otp_code: str
    new_password: str

# 1. Запрос кода для сброса пароля
@app.post("/api/v1/auth/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь с таким Email не найден")

    otp = str(random.randint(100000, 999999))
    user.otp_code = otp
    user.otp_expire = datetime.utcnow() + timedelta(minutes=5)
    db.commit()

    send_otp_email(user.email, otp)
    return {"message": "Код для сброса пароля отправлен на почту"}

# 2. Установка нового пароля
@app.post("/api/v1/auth/reset-password")
def reset_password(data: ResetPasswordConfirm, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user or user.otp_code != data.otp_code:
        raise HTTPException(status_code=400, detail="Неверный код или Email")

    if datetime.utcnow() > user.otp_expire:
        raise HTTPException(status_code=400, detail="Срок действия кода истек")

    user.hashed_password = hash_password(data.new_password)
    user.otp_code = None # Очищаем код
    db.commit()
    return {"message": "Пароль успешно изменен"}

# 3. Переотправка OTP (универсальный для регистрации и сброса)
@app.post("/api/v1/auth/resend-otp")
def resend_otp(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    otp = str(random.randint(100000, 999999))
    user.otp_code = otp
    user.otp_expire = datetime.utcnow() + timedelta(minutes=5)
    db.commit()
    
    send_otp_email(user.email, otp)
    return {"message": "Новый код отправлен"}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

# Функция для получения текущего пользователя по токену
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Недействительный токен")
    except Exception:
        raise HTTPException(status_code=401, detail="Ошибка авторизации")
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user

# Схемы для обновления
class UserUpdate(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: str

# 1. Получение данных профиля
@app.get("/api/v1/users/me")
def read_user_me(current_user: models.User = Depends(get_current_user)):
    return {
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "username": current_user.username,
        "email": current_user.email,
        "avatar_url": current_user.avatar_url 
    }

# 2. Обновление профиля
@app.patch("/api/v1/users/me")
def update_user_me(data: UserUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    current_user.first_name = data.first_name
    current_user.last_name = data.last_name
    current_user.username = data.username
    current_user.email = data.email
    db.commit()
    return {"message": "Профиль обновлен успешно"}

# Схемы
class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class AvatarUpdate(BaseModel):
    avatar_url: str

# 1. Смена пароля
@app.patch("/api/v1/users/me/password")
def change_password(data: PasswordChange, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Проверяем старый пароль
    if hash_password(data.old_password) != current_user.hashed_password:
        raise HTTPException(status_code=400, detail="Старый пароль введен неверно")
    
    # Хэшируем и сохраняем новый
    current_user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"message": "Пароль успешно изменен"}

# 2. Обновление ссылки на аватар
@app.patch("/api/v1/users/me/avatar")
def update_avatar(data: AvatarUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    current_user.avatar_url = data.avatar_url # Не забудьте добавить это поле в models.py (String, nullable=True)
    db.commit()
    return {"message": "Аватар обновлен"}