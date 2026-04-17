from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, List
import models, hashlib, jwt, random, os, cloudinary, cloudinary.uploader
from datetime import datetime, timedelta
from pydantic import BaseModel
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# --- 1. ИНИЦИАЛИЗАЦИЯ И НАСТРОЙКИ ---
Base.metadata.create_all(bind=engine)

cloudinary.config(
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
  api_key = os.getenv("CLOUDINARY_API_KEY"),
  api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

app = FastAPI(title="TrackLane API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "tracklane_super_secret_key_rpo_coursework"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise HTTPException(status_code=401)
    except: raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None: raise HTTPException(status_code=401, detail="User not found")
    return user

def send_otp_email(receiver_email: str, otp_code: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
    if not sender_email or not sender_password: return
    msg = MIMEMultipart()
    msg['Subject'] = "Код подтверждения TrackLane"
    body = f"Ваш код подтверждения: {otp_code}. Действителен 5 минут."
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP_SSL('smtp.mail.ru', 465)
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
    except Exception as e: print(f"Email error: {e}")

# --- 3. СХЕМЫ ДАННЫХ (PYDANTIC) ---

class UserRegister(BaseModel):
    first_name: str; last_name: str; username: str; email: str; password: str
class UserLogin(BaseModel):
    username: str; password: str
class OTPVerify(BaseModel):
    email: str; otp_code: str
class ForgotPasswordRequest(BaseModel):
    email: str
class ResetPasswordConfirm(BaseModel):
    email: str; otp_code: str; new_password: str
class UserUpdate(BaseModel):
    first_name: str; last_name: str; username: str; email: str
class PasswordChange(BaseModel):
    old_password: str; new_password: str
class AvatarUpdate(BaseModel):
    avatar_url: Optional[str] = None
class ProjectCreate(BaseModel):
    title: str; description: Optional[str] = None
class ProjectUpdate(BaseModel):
    title: str; description: Optional[str] = None
class ColumnCreate(BaseModel):
    title: str; wip_limit: int; project_id: int
class TaskCreate(BaseModel):
    title: str; description: Optional[str] = None; column_id: int; priority: str = "Medium"

# --- 4. МАРШРУТЫ: АВТОРИЗАЦИЯ ---

@app.post("/api/v1/auth/register")
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email уже занят")
    otp = str(random.randint(100000, 999999))
    new_user = models.User(
        first_name=user.first_name, last_name=user.last_name, username=user.username,
        email=user.email, hashed_password=hash_password(user.password),
        otp_code=otp, otp_expire=datetime.utcnow() + timedelta(minutes=5)
    )
    db.add(new_user); db.commit()
    send_otp_email(user.email, otp)
    return {"message": "Успех", "dev_otp": otp}

@app.post("/api/v1/auth/verify-otp")
def verify_otp(data: OTPVerify, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user or user.otp_code != data.otp_code:
        raise HTTPException(status_code=400, detail="Неверный код")
    user.is_active = True; user.otp_code = None; db.commit()
    return {"message": "Email подтвержден"}

@app.post("/api/v1/auth/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if not db_user or not db_user.is_active:
        raise HTTPException(status_code=401, detail="Аккаунт не активен или не найден")
    if db_user.hashed_password != hash_password(user.password):
        raise HTTPException(status_code=400, detail="Неверный пароль")
    return {"token": create_access_token({"sub": db_user.username}), "username": db_user.username}

# --- 5. МАРШРУТЫ: ПРОФИЛЬ ---

@app.get("/api/v1/users/me")
def read_user_me(u: models.User = Depends(get_current_user)):
    return {"first_name": u.first_name, "last_name": u.last_name, "username": u.username, "email": u.email, "avatar_url": u.avatar_url}

@app.patch("/api/v1/users/me/avatar")
def update_avatar(data: AvatarUpdate, db: Session = Depends(get_db), u: models.User = Depends(get_current_user)):
    if u.avatar_url and not data.avatar_url:
        try:
            public_id = u.avatar_url.split('/')[-1].split('.')[0]
            cloudinary.uploader.destroy(public_id)
        except: pass
    u.avatar_url = data.avatar_url; db.commit()
    return {"message": "Updated"}

@app.get("/api/v1/users/search")
def search_users(query: str, db: Session = Depends(get_db), u: models.User = Depends(get_current_user)):
    users = db.query(models.User).filter(models.User.username.ilike(f"%{query}%"), models.User.id != u.id).all()
    return [{"id": usr.id, "username": usr.username, "avatar_url": usr.avatar_url} for usr in users]

# --- 6. МАРШРУТЫ: ПРОЕКТЫ И КОМАНДА ---

@app.post("/api/v1/projects")
def create_project(data: ProjectCreate, db: Session = Depends(get_db), u: models.User = Depends(get_current_user)):
    new_p = models.Project(title=data.title, description=data.description, owner_id=u.id)
    db.add(new_p); db.commit(); db.refresh(new_p)
    # Создатель - админ
    db.add(models.ProjectMember(project_id=new_p.id, user_id=u.id, role="admin"))
    # Сразу создаем базовые колонки Канбана
    base_cols = ["Запланировано", "В процессе", "На рассмотрении", "Готово"]
    for col_title in base_cols:
        db.add(models.ColumnModel(title=col_title, project_id=new_p.id, wip_limit=0))
    db.commit()
    return new_p

@app.get("/api/v1/projects")
def list_projects(db: Session = Depends(get_db), u: models.User = Depends(get_current_user)):
    memberships = db.query(models.ProjectMember).filter_by(user_id=u.id).all()
    p_ids = [m.project_id for m in memberships]
    projects = db.query(models.Project).filter(models.Project.id.in_(p_ids)).all()
    return projects

@app.get("/api/v1/projects/{project_id}/members")
def get_members(project_id: int, db: Session = Depends(get_db)):
    mems = db.query(models.ProjectMember).filter_by(project_id=project_id).all()
    return [{"user_id": m.user_id, "username": m.user.username, "role": m.role} for m in mems]

@app.post("/api/v1/projects/{project_id}/members")
def add_member(project_id: int, user_id: int, role: str, db: Session = Depends(get_db)):
    db.add(models.ProjectMember(project_id=project_id, user_id=user_id, role=role))
    db.commit()
    return {"message": "Added"}

# --- 7. МАРШРУТЫ: КАНБАН (КОЛОНКИ И ЗАДАЧИ) ---

@app.get("/api/v1/projects/{project_id}/columns")
def get_columns(project_id: int, db: Session = Depends(get_db)):
    cols = db.query(models.ColumnModel).filter_by(project_id=project_id).all()
    res = []
    for c in cols:
        count = db.query(models.Task).filter_by(column_id=c.id).count()
        res.append({"id": c.id, "title": c.title, "wip_limit": c.wip_limit, "task_count": count})
    return res

@app.post("/api/v1/tasks/")
def create_task(t: TaskCreate, db: Session = Depends(get_db)):
    col = db.query(models.ColumnModel).filter_by(id=t.column_id).first()
    if col.wip_limit > 0:
        count = db.query(models.Task).filter_by(column_id=t.column_id).count()
        if count >= col.wip_limit: raise HTTPException(status_code=400, detail="WIP_LIMIT_EXCEEDED")
    new_t = models.Task(title=t.title, description=t.description, column_id=t.column_id, priority=t.priority)
    db.add(new_t); db.commit(); db.refresh(new_t)
    return new_t

@app.get("/api/v1/columns/{column_id}/tasks")
def get_tasks_by_col(column_id: int, db: Session = Depends(get_db)):
    return db.query(models.Task).filter_by(column_id=column_id).all()