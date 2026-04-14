from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="TrackLane API",
    description="Backend for TrackLane Mobile App (РПО Курсовая)",
    version="1.0.0"
)

# Настройка CORS для свободного доступа с мобильного приложения (Expo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "TrackLane API is running! Сервер успешно запущен."}

# Фича из курсовой (Раздел 3.4.3: Проверка WIP лимитов)
@app.put("/api/v1/tasks/{task_id}/move")
def move_task(task_id: int, target_column_id: int):
    # Позже мы подключим настоящую базу данных PostgreSQL из Firebase
    current_tasks = 5
    wip_limit = 5
    
    # Строгий контроль WIP-лимитов на бэкенде
    if current_tasks >= wip_limit:
        raise HTTPException(
            status_code=400,
            detail="WIP_LIMIT_EXCEEDED"
        )
    return {"message": "Задача успешно перемещена"}