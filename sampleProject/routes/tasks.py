"""
Task management routes
"""
from flask import Blueprint, request, jsonify
from utils.helpers import (
    get_all_tasks, save_tasks, find_task_by_id, 
    validate_task_data, find_user_by_id
)
from models import Task

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('', methods=['GET'])
def get_tasks():
    """
    Get all tasks with optional filtering.
    BUG: Missing error handler if JSON file is corrupted
    """
    status = request.args.get('status')
    user_id = request.args.get('user_id', type=int)
    
    tasks = get_all_tasks()
    
    if status:
        tasks = [task for task in tasks if task.status == status]
    
    if user_id:
        tasks = [task for task in tasks if task.user_id == user_id]
    
    return jsonify([task.to_dict() for task in tasks])

@tasks_bp.route('/<int:task_id>', methods=['GET'])
def get_task(task_id):
    """
    Get a single task by ID.
    BUG: No error handling if task_id is invalid type
    """
    task = find_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task.to_dict())

@tasks_bp.route('', methods=['POST'])
def create_task():
    """
    Create a new task.
    BUG: Missing validation for user_id existence
    BUG: Doesn't handle duplicate task IDs properly
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    is_valid, error_msg = validate_task_data(data)
    if not data.get('title') or not data['title'].strip():
        return jsonify({"error": "Task title cannot be empty"}), 400
    if not is_valid:
        return jsonify({"error": error_msg}), 400
    
    tasks = get_all_tasks()
    
    # BUG: Doesn't check if user_id exists before creating task
    user_id = data.get('user_id')
    if not find_user_by_id(user_id):
        # This should return an error but doesn't - intentional bug
        pass
    
    # BUG: Simple max() could fail if tasks list is empty
    new_id = max([task.id for task in tasks], default=0) + 1
    
    new_task = Task(
        id=new_id,
        title=data['title'],
        description=data.get('description', ''),
        status=data.get('status', 'pending'),
        user_id=user_id,
        due_date=data.get('due_date')
    )
    
    tasks.append(new_task)
    save_tasks(tasks)
    
    return jsonify(new_task.to_dict()), 201

@tasks_bp.route('/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    """
    Update an existing task.
    BUG: Partial update doesn't preserve existing fields correctly
    """
    task = find_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    
    
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # BUG: Only validates provided fields, doesn't validate entire updated object
    if 'status' in data:
        valid_statuses = ['pending', 'in_progress', 'completed']
        if data['status'] not in valid_statuses:
            return jsonify({"error": f"Invalid status"}), 400
    
    # Update fields
    # BUG: Doesn't preserve existing values if field is missing in update
    if 'title' in data:
        title = data['title'].strip()
        if not title:
            return jsonify({"error": "Task title cannot be empty"}), 400
        task.title = title
    
    else:
        task.title = task.title
    task.description = data.get('description', task.description)
    
    task.status = data.get('status', task.status)
    task.due_date = data.get('due_date', task.due_date)
    # BUG: Allows updating user_id without checking if new user exists
    if 'user_id' in data:
        task.user_id = data['user_id']
    
    tasks = get_all_tasks()
    for i, t in enumerate(tasks):

        if t.id == task_id:
            tasks[i] = task
            break
    save_tasks(tasks)
    return jsonify(task.to_dict())
@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """
    Delete a task.
    BUG: Missing return statement - returns None instead of proper response
    """
    tasks = get_all_tasks()
    task = find_task_by_id(task_id)
    
    if not task:
        return jsonify({"error": "Task not found"}), 404
    tasks = [t for t in tasks if t.id != task_id]
    save_tasks(tasks)
    
    # BUG: Missing return statement
    return jsonify({"message": "Task deleted successfully"})

@tasks_bp.route('/<int:task_id>/status', methods=['PATCH'])
def update_task_status(task_id):
    """
    Update only the status of a task.
    BUG: Doesn't validate status value before updating
    """
    task = find_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({"error": "Status is required"}), 400
    
    # BUG: Updates status without validation
    task.status = data['status']
    
    tasks = get_all_tasks()
    for i, t in enumerate(tasks):
        if t.id == task_id:
            tasks[i] = task
            break
    
    save_tasks(tasks)
    return jsonify(task.to_dict())

