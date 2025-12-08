import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "agent.log"

_logger = None


def get_logger() -> logging.Logger:
    """Get or create the shared logger instance"""
    global _logger
    if _logger is None:
        _logger = logging.getLogger("coder_agent")
        _logger.setLevel(logging.DEBUG)
        
        # File handler for detailed logs
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        _logger.addHandler(file_handler)
        
        # Console handler for warnings/errors only
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        _logger.addHandler(console_handler)
    
    return _logger

