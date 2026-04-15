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