# Task Manager API

A simple RESTful Task Manager API built with Flask that uses JSON files as a database. This project is designed for testing and learning purposes, and contains several intentional bugs for agents to identify and fix.

## Project Overview

This Task Manager API allows users to:
- Create, read, update, and delete tasks
- Manage users who own tasks
- Filter tasks by status and user
- Update task status independently

The API uses JSON files (`data/tasks.json` and `data/users.json`) to store data, making it easy to understand and modify without requiring a database setup.

## Project Structure

```
sampleProject/
├── main.py                 # Flask application entry point
├── models.py              # Data models (Task, User)
├── routes/
│   ├── tasks.py           # Task management endpoints
│   └── users.py           # User management endpoints
├── utils/
│   └── helpers.py         # Helper functions for JSON operations
├── tests/
│   └── test_tasks.py      # Test suite (incomplete coverage)
├── data/
│   ├── tasks.json         # Tasks database (8 sample tasks)
│   └── users.json         # Users database (5 sample users)
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Features

### Task Management
- **GET** `/api/tasks` - Get all tasks (supports `?status=` and `?user_id=` filters)
- **GET** `/api/tasks/<id>` - Get a specific task
- **POST** `/api/tasks` - Create a new task
- **PUT** `/api/tasks/<id>` - Update a task
- **PATCH** `/api/tasks/<id>/status` - Update only task status
- **DELETE** `/api/tasks/<id>` - Delete a task

### User Management
- **GET** `/api/users` - Get all users
- **GET** `/api/users/<id>` - Get a specific user
- **POST** `/api/users` - Create a new user
- **PUT** `/api/users/<id>` - Update a user
- **DELETE** `/api/users/<id>` - Delete a user

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python main.py
```

The API will be available at `http://localhost:5000`

## Sample Data

The project comes with pre-populated dummy data:

- **5 Users**: John Doe, Jane Smith, Bob Johnson, Alice Williams, Charlie Brown
- **8 Tasks**: Various tasks in different states (pending, in_progress, completed)

## API Usage Examples

### Get all tasks
```bash
curl http://localhost:5000/api/tasks
```

### Get tasks by status
```bash
curl http://localhost:5000/api/tasks?status=pending
```

### Create a new task
```bash
curl -X POST http://localhost:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New Task",
    "description": "Task description",
    "status": "pending",
    "user_id": 1,
    "due_date": "2024-03-01"
  }'
```

### Update a task
```bash
curl -X PUT http://localhost:5000/api/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title",
    "status": "completed"
  }'
```

### Delete a task
```bash
curl -X DELETE http://localhost:5000/api/tasks/1
```

## Running Tests

```bash
pytest tests/test_tasks.py -v
```

## Known Issues (Intentional Bugs)

This project contains several intentional bugs for testing purposes. Here are some categories of issues to look for:

### 1. **Error Handling Issues**
- Missing error handlers for file operations
- No handling for corrupted JSON files
- Missing error responses in some endpoints

### 2. **Validation Bugs**
- Incomplete validation logic (allows empty strings, invalid formats)
- Missing validation for required relationships (e.g., user_id existence)
- Date format validation is incomplete

### 3. **Data Integrity Issues**
- No duplicate checking (emails, task IDs)
- Missing validation when updating relationships
- Race conditions in concurrent file writes

### 4. **Logic Errors**
- Missing return statements
- Incorrect comparison operators
- Edge cases not handled (empty lists, None values)

### 5. **Test Coverage**
- Incomplete test suite
- Missing tests for error cases
- Missing tests for edge cases

### 6. **Business Logic Issues**
- Deleting users without checking for associated tasks
- Allowing invalid status updates
- Not preserving existing data during partial updates

## Bug Hunting Guide

To find and fix bugs, consider:

1. **Test edge cases**: Empty strings, None values, invalid IDs, concurrent requests
2. **Check validation**: Try creating tasks/users with invalid data
3. **Test relationships**: Create tasks with non-existent user_ids, delete users with tasks
4. **Check error handling**: Corrupt JSON files, missing files, invalid requests
5. **Review return values**: Some endpoints may not return proper responses
6. **Test concurrent operations**: Multiple simultaneous writes to JSON files

## Expected Task Status Values

- `pending` - Task is not yet started
- `in_progress` - Task is currently being worked on
- `completed` - Task is finished

## Data Format

### Task Object
```json
{
  "id": 1,
  "title": "Task title",
  "description": "Task description",
  "status": "pending",
  "user_id": 1,
  "due_date": "2024-02-15",
  "created_at": "2024-01-20T08:00:00"
}
```

### User Object
```json
{
  "id": 1,
  "name": "John Doe",
  "email": "john.doe@example.com",
  "created_at": "2024-01-15T10:30:00"
}
```

## Notes

- The JSON database files are created automatically if they don't exist
- All timestamps are in ISO 8601 format
- Task IDs and User IDs are auto-incremented
- The API runs in debug mode by default (not suitable for production)

## License

This is a sample project for educational purposes.

