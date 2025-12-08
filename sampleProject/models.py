"""
Data models for Task Manager API
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

class Task:
    def __init__(self, id: int, title: str, description: str, 
                 status: str, user_id: int, due_date: Optional[str] = None,
                 created_at: Optional[str] = None):
        self.id = id
        self.title = title
        self.description = description
        self.status = status  # 'pending', 'in_progress', 'completed'
        self.user_id = user_id
        self.due_date = due_date
        self.created_at = created_at or datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "user_id": self.user_id,
            "due_date": self.due_date,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        return cls(
            id=data.get("id"),
            title=data.get("title"),
            description=data.get("description"),
            status=data.get("status"),
            user_id=data.get("user_id"),
            due_date=data.get("due_date"),
            created_at=data.get("created_at")
        )

class User:
    def __init__(self, id: int, name: str, email: str, created_at: Optional[str] = None):
        self.id = id
        self.name = name
        self.email = email
        self.created_at = created_at or datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        return cls(
            id=data.get("id"),
            name=data.get("name"),
            email=data.get("email"),
            created_at=data.get("created_at")
        )

