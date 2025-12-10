"""
Configuration
"""
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent / "sampleProject"

# LLM - DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL_MAIN = "deepseek-chat"
MODEL_FAST = "deepseek-chat"

# Memory
MAX_SESSION_FILES = 30
MAX_CONVERSATION_HISTORY = 10
MAX_CONTEXT_CHARS = 40000
CACHE_SIZE = 500

# Execution
COMMAND_TIMEOUT = 30

