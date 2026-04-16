from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=True)    # Имя
    last_name = Column(String, nullable=True)     # Фамилия
    username = Column(String, unique=True, index=True, nullable=False) # Псевдоним
    email = Column(String, unique=True, index=True, nullable=False)    # Email
    hashed_password = Column(String, nullable=False) # Зашифрованный пароль
    
    role = Column(String, default="Member") # Admin, Member, Reviewer
    is_active = Column(Boolean, default=False) # Станет True после ввода OTP кода

    tasks = relationship("Task", back_populates="assignee")
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)

    columns = relationship("ColumnModel", back_populates="project")

class ColumnModel(Base):
    __tablename__ = "columns"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False) # Например: "To Do", "In Progress"
    wip_limit = Column(Integer, nullable=False, default=0) # КЛЮЧЕВАЯ ФИЧА КУРСОВОЙ (0 = без лимита)
    project_id = Column(Integer, ForeignKey("projects.id"))

    project = relationship("Project", back_populates="columns")
    tasks = relationship("Task", back_populates="column")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String, default="Medium") # High, Medium, Low (Раздел 3.4.5)
    deadline = Column(DateTime, default=datetime.datetime.utcnow)
    
    column_id = Column(Integer, ForeignKey("columns.id"))
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    column = relationship("ColumnModel", back_populates="tasks")
    assignee = relationship("User", back_populates="tasks")