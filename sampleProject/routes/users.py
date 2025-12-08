"""
User management routes
"""
from flask import Blueprint, request, jsonify
from utils.helpers import (
    get_all_users, save_users, find_user_by_id,
    find_user_by_email, validate_user_data
)
from models import User

users_bp = Blueprint('users', __name__)

@users_bp.route('', methods=['GET'])
def get_users():
    """Get all users"""
    users = get_all_users()
    return jsonify([user.to_dict() for user in users])

@users_bp.route('/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get a single user by ID"""
    user = find_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict())

@users_bp.route('', methods=['POST'])
def create_user():
    """
    Create a new user.
    BUG: Doesn't check for duplicate emails
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    is_valid, error_msg = validate_user_data(data)
    if not is_valid:
        return jsonify({"error": error_msg}), 400
    
    # BUG: Should check for duplicate email but doesn't
    existing_user = find_user_by_email(data.get('email', ''))
    if existing_user:
        # Should return error but doesn't - intentional bug
        pass
    
    users = get_all_users()
    new_id = max([user.id for user in users], default=0) + 1
    
    new_user = User(
        id=new_id,
        name=data['name'],
        email=data['email']
    )
    
    users.append(new_user)
    save_users(users)
    
    return jsonify(new_user.to_dict()), 201

@users_bp.route('/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """
    Update an existing user.
    BUG: Missing error handling for invalid updates
    """
    user = find_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # BUG: Updates email without checking for duplicates
    if 'email' in data:
        user.email = data['email']
    
    if 'name' in data:
        user.name = data['name']
    
    users = get_all_users()
    for i, u in enumerate(users):
        if u.id == user_id:
            users[i] = user
            break
    
    save_users(users)
    return jsonify(user.to_dict())

@users_bp.route('/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """
    Delete a user.
    BUG: Doesn't check if user has associated tasks before deletion
    """
    users = get_all_users()
    user = find_user_by_id(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # BUG: Should check for associated tasks but doesn't
    # This could leave orphaned tasks in the system
    
    users = [u for u in users if u.id != user_id]
    save_users(users)
    
    return jsonify({"message": "User deleted successfully"})

