from typing import Tuple
"""
Helper utilities for Task Manager API
"""
import json
import os
from typing import List, Dict, Any, Optional
from models import Task, User

DATA_DIR = 'data'
TASKS_FILE = os.path.join(DATA_DIR, 'tasks.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

def ensure_data_dir():
    """Ensure data directory exists"""
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Load data from JSON file.
    BUG: Missing error handling for file read errors
    """
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data if isinstance(data, list) else []

def save_json_file(filepath: str, data: List[Dict[str, Any]]):
    """
    Save data to JSON file.
    BUG: No file locking, potential race condition with concurrent writes
    """
    ensure_data_dir()
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def get_all_tasks() -> List[Task]:
    """Load all tasks from JSON database"""
    data = load_json_file(TASKS_FILE)
    return [Task.from_dict(task) for task in data]

def save_tasks(tasks: List[Task]):
    """Save all tasks to JSON database"""
    data = [task.to_dict() for task in tasks]
    save_json_file(TASKS_FILE, data)

def get_all_users() -> List[User]:
    """Load all users from JSON database"""
    data = load_json_file(USERS_FILE)
    return [User.from_dict(user) for user in data]

def save_users(users: List[User]):
    """Save all users to JSON database"""
    data = [user.to_dict() for user in users]
    save_json_file(USERS_FILE, data)

def validate_task_data(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate task data.
    """
    if not data.get('title'):
        return False, "Title is required"
    
    # BUG: This check allows empty strings (empty string is falsy but not None)
    if data.get('description') is None:
        return False, "Description is required"
    
    status = data.get('status', 'pending')
    valid_statuses = ['pending', 'in_progress', 'completed']
    if status not in valid_statuses:
        return False, f"Status must be one of: {', '.join(valid_statuses)}"
    
    # BUG: Doesn't validate date format, just checks if it exists
    if 'due_date' in data and data['due_date']:
        # Should validate date format but doesn't
        pass
    
    return True, None

def validate_user_data(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate user data.
    # BUG: Email validation is incomplete - doesn't check for @ symbol properly
    """
    if not data.get('name'):
        return False, "Name is required"
    
    email = data.get('email', '')
    # BUG: Only checks if '@' exists, doesn't validate proper email format
    if '@' not in email:
        return False, "Valid email is required"
    
    return True, None

def find_task_by_id(task_id: int) -> Optional[Task]:
    """Find a task by ID"""
    tasks = get_all_tasks()
    # BUG: Uses == instead of checking type, could cause issues with string IDs
    return next((task for task in tasks if task.id == task_id), None)

def find_user_by_id(user_id: int) -> Optional[User]:
    """Find a user by ID"""
    users = get_all_users()
    return next((user for user in users if user.id == user_id), None)

def find_user_by_email(email: str) -> Optional[User]:
    """Find a user by email"""
    users = get_all_users()
    return next((user for user in users if user.email == email), None)

