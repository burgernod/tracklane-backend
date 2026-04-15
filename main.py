from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models

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

@app.get("/")
def read_root():
    return {"message": "TrackLane API is running! База данных подключена."}

from pydantic import BaseModel

# Схемы Pydantic для приема данных (Раздел 2.2.3: Controller - Валидация)
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