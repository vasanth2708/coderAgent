"""
Test suite for Task Manager API
BUG: Incomplete test coverage - missing tests for error cases and edge cases
"""
import pytest
import json
import os
import sys
from flask import Flask

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from utils.helpers import get_all_tasks, save_tasks, TASKS_FILE

@pytest.fixture
def client():
    """Create a test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def sample_task():
    """Sample task data for testing"""
    return {
        "title": "Test Task",
        "description": "This is a test task",
        "status": "pending",
        "user_id": 1,
        "due_date": "2024-02-20"
    }

def test_get_tasks(client):
    """Test getting all tasks"""
    response = client.get('/api/tasks')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)

def test_get_task_by_id(client):
    """Test getting a single task"""
    # First create a task to ensure we have one to retrieve
    task_data = {
        "title": "Test Task for Get",
        "description": "Test description",
        "status": "pending",
        "user_id": 1
    }
    create_response = client.post('/api/tasks',
                                 data=json.dumps(task_data),
                                 content_type='application/json')
    created_task = json.loads(create_response.data)
    
    response = client.get(f'/api/tasks/{created_task["id"]}')
    assert response.status_code == 200
def test_create_task(client, sample_task):
    response = client.post('/api/tasks',
        data=json.dumps(sample_task),
        content_type='application/json')
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['title'] == sample_task['title']

def test_create_task_missing_title(client):
    """Test creating a task without title"""
    task_data = {
        "description": "No title",
        "status": "pending",
        "user_id": 1
    }
    response = client.post('/api/tasks',
                          data=json.dumps(task_data),
content_type='application/json')
    assert response.status_code == 400

def test_update_task(client, sample_task):
    """Test updating a task"""
    update_data = {
        "title": "Updated Task Title",
        "status": "completed"
    }
    # First create a task to ensure we have one to update
    create_response = client.post('/api/tasks',
                                 data=json.dumps(sample_task),
                                 content_type='application/json')
    created_task = json.loads(create_response.data)
    
    response = client.put(f'/api/tasks/{created_task["id"]}',
                         data=json.dumps(update_data),
                         content_type='application/json')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['title'] == "Updated Task Title"
    assert data['status'] == "completed"

# BUG: Missing tests for:
# - Testing task deletion
# - Testing status update endpoint
# - Testing filtering by status
# - Testing filtering by user_id
# - Testing invalid status values
# - Testing concurrent updates
# - Testing edge cases (empty strings, None values, etc.)

