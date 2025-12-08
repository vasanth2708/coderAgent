from flask import Flask, jsonify
from routes.tasks import tasks_bp
from routes.users import users_bp
import os

app = Flask(__name__)

# Register blueprints
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(users_bp, url_prefix='/api/users')

@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Task Manager API is running"})

@app.route('/api/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    app.run(debug=True, port=8000)

