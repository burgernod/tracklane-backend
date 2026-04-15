from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default="Member") # В курсовой роли: Admin, Member, Reviewer

    # Связи (для курсовой не обязательно прописывать всё сложно, но оставим задел на будущее)
    tasks = relationship("Task", back_populates="assignee")

class Project(Base):
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