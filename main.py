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
from typing import Optional
import cloudinary
import cloudinary.uploader

# Настройка (вставьте свои данные)
cloudinary.config(
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
  api_key = os.getenv("CLOUDINARY_API_KEY"),
  api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

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
    avatar_url: Optional[str] = None

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
    # Если мы хотим удалить старое фото из Cloudinary
    if current_user.avatar_url and (data.avatar_url is None):
        try:
            # Извлекаем public_id из URL (это часть между последним / и расширением)
            public_id = current_user.avatar_url.split('/')[-1].split('.')[0]
            cloudinary.uploader.destroy(public_id)
        except Exception as e:
            print(f"Ошибка удаления из Cloudinary: {e}")

    current_user.avatar_url = data.avatar_url
    db.commit()
    return {"message": "Аватар обновлен"}

# --- 1. SEARCH USERS (Для поиска как в почте) ---
@app.get("/api/v1/users/search")
def search_users(query: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Ищем по части username или email, исключая себя
    users = db.query(models.User).filter(
        (models.User.username.ilike(f"%{query}%")) | (models.User.email.ilike(f"%{query}%")),
        models.User.id != current_user.id
    ).limit(10).all()
    
    return [{"id": u.id, "username": u.username, "email": u.email, "avatar_url": u.avatar_url} for u in users]

# --- 2. PROJECTS LOGIC ---
class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None

@app.post("/api/v1/projects")
def create_project(data: ProjectCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    new_project = models.Project(title=data.title, description=data.description, owner_id=current_user.id)
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    
    # Сразу добавляем создателя как ADMIN
    member = models.ProjectMember(project_id=new_project.id, user_id=current_user.id, role="admin")
    db.add(member)
    db.commit()
    return new_project

@app.post("/api/v1/projects/{project_id}/members")
def add_member(project_id: int, user_id: int, role: str, db: Session = Depends(get_db)):
    # Проверка на дубликат
    exists = db.query(models.ProjectMember).filter_by(project_id=project_id, user_id=user_id).first()
    if exists:
        raise HTTPException(status_code=400, detail="Пользователь уже в проекте")
    
    new_mem = models.ProjectMember(project_id=project_id, user_id=user_id, role=role)
    db.add(new_mem)
    db.commit()
    return {"message": "Участник добавлен"}

# main.py — добавить в конец файла

# --- СХЕМЫ ---
class ProjectUpdate(BaseModel):
    title: str
    description: Optional[str] = None

# --- ПОЛУЧИТЬ ВСЕ ПРОЕКТЫ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ ---
@app.get("/api/v1/projects")
def get_my_projects(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Проекты где пользователь является участником (через ProjectMember)
    memberships = db.query(models.ProjectMember).filter(
        models.ProjectMember.user_id == current_user.id
    ).all()
    
    project_ids = [m.project_id for m in memberships]
    projects = db.query(models.Project).filter(models.Project.id.in_(project_ids)).all()
    
    result = []
    for p in projects:
        # Считаем задачи проекта (через колонки)
        member_count = db.query(models.ProjectMember).filter(
            models.ProjectMember.project_id == p.id
        ).count()
        
        # Роль текущего пользователя в этом проекте
        my_membership = next((m for m in memberships if m.project_id == p.id), None)
        
        result.append({
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "image_url": p.image_url,  # добавим в модель ниже
            "member_count": member_count,
            "my_role": my_membership.role if my_membership else "member",
            "owner_id": p.owner_id,
        })
    
    return result

# --- ПОЛУЧИТЬ УЧАСТНИКОВ ПРОЕКТА ---
@app.get("/api/v1/projects/{project_id}/members")
def get_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Проверяем что текущий юзер состоит в проекте
    my_membership = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=current_user.id
    ).first()
    if not my_membership:
        raise HTTPException(status_code=403, detail="Нет доступа к этому проекту")
    
    memberships = db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id
    ).all()
    
    result = []
    for m in memberships:
        user = db.query(models.User).filter(models.User.id == m.user_id).first()
        if user:
            result.append({
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "avatar_url": user.avatar_url,
                "role": m.role,
                "is_me": user.id == current_user.id,
            })
    
    return result

# --- УДАЛИТЬ УЧАСТНИКА ИЗ ПРОЕКТА ---
@app.delete("/api/v1/projects/{project_id}/members/{user_id}")
def remove_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Только админ может удалять
    my_membership = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=current_user.id
    ).first()
    if not my_membership or my_membership.role != "admin":
        raise HTTPException(status_code=403, detail="Только администратор может удалять участников")
    
    # Нельзя удалить владельца проекта
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project.owner_id == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить владельца проекта")
    
    membership = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=user_id
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Участник не найден")
    
    db.delete(membership)
    db.commit()
    return {"message": "Участник удалён"}

# --- ОБНОВИТЬ ПРОЕКТ (название, описание, фото) ---
@app.patch("/api/v1/projects/{project_id}")
def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    my_membership = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=current_user.id
    ).first()
    if not my_membership or my_membership.role != "admin":
        raise HTTPException(status_code=403, detail="Только администратор может редактировать проект")
    
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    
    project.title = data.title
    project.description = data.description
    db.commit()
    return {"message": "Проект обновлён"}

# --- ОБНОВИТЬ ФОТО ПРОЕКТА ---
class ProjectImageUpdate(BaseModel):
    image_url: Optional[str] = None

@app.patch("/api/v1/projects/{project_id}/image")
def update_project_image(
    project_id: int,
    data: ProjectImageUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    my_membership = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=current_user.id
    ).first()
    if not my_membership or my_membership.role != "admin":
        raise HTTPException(status_code=403, detail="Только администратор может менять фото")
    
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")

    # Удаляем старое фото из Cloudinary если оно было
    if project.image_url and data.image_url is None:
        try:
            public_id = project.image_url.split('/')[-1].split('.')[0]
            cloudinary.uploader.destroy(public_id)
        except Exception as e:
            print(f"Ошибка удаления фото проекта из Cloudinary: {e}")
    
    project.image_url = data.image_url
    db.commit()
    return {"message": "Фото проекта обновлено"}

# --- УДАЛИТЬ ПРОЕКТ ---
@app.delete("/api/v1/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    
    # Только владелец может удалить проект
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Только владелец может удалить проект")
    
    # Каскадно удаляем участников (задачи и колонки — если настроено cascade в моделях)
    db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id
    ).delete()
    
    db.delete(project)
    db.commit()
    return {"message": "Проект удалён"}