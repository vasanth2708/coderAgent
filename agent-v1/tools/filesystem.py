"""
Filesystem Tools - Direct implementations
"""
import os
from pathlib import Path
from typing import List

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "sampleProject"


def list_files() -> List[str]:
    """List all Python files in project"""
    files = []
    for root, _, filenames in os.walk(PROJECT_DIR):
        for f in filenames:
            if f.endswith(".py"):
                rel = str(Path(root, f).relative_to(PROJECT_DIR))
                files.append(rel)
    return sorted(files)


def read_file(filepath: str) -> str:
    """Read file content"""
    return (PROJECT_DIR / filepath).read_text(encoding="utf-8")


def write_file(filepath: str, content: str):
    """Write file content"""
    (PROJECT_DIR / filepath).write_text(content, encoding="utf-8")


def backup_file(filepath: str) -> str:
    """Create backup, return backup content"""
    return read_file(filepath)


def restore_file(filepath: str, content: str):
    """Restore file from backup"""
    write_file(filepath, content)

