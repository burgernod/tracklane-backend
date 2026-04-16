from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="Member")
    is_active = Column(Boolean, default=False)

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
    title = Column(String, nullable=False)
    wip_limit = Column(Integer, nullable=False, default=0)
    project_id = Column(Integer, ForeignKey("projects.id"))

    project = relationship("Project", back_populates="columns")
    tasks = relationship("Task", back_populates="column")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String, default="Medium")
    deadline = Column(DateTime, default=datetime.datetime.utcnow)
    
    column_id = Column(Integer, ForeignKey("columns.id"))
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True) # ИМЕННО ЭТА СТРОКА ТЕРЯЛАСЬ!

    column = relationship("ColumnModel", back_populates="tasks")
    assignee = relationship("User", back_populates="tasks")