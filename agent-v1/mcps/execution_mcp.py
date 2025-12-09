import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import ray

from config.logger_config import get_logger

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_PROJECT_DIR = BASE_DIR / "../sampleProject"
COMMAND_TIMEOUT = 30  # seconds

logger = get_logger()


@ray.remote
def _run_command(command: list[str]) -> Dict[str, str]:
    proc = subprocess.Popen(
        command,
        cwd=SAMPLE_PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        text=True,
    )
    try:
        out, _ = proc.communicate(timeout=COMMAND_TIMEOUT)
        return {"exit_code": proc.returncode, "stdout": out, "stderr": ""}
    except subprocess.TimeoutExpired:
        logger.warning(f"Command {command} exceeded timeout of {COMMAND_TIMEOUT} seconds, terminating...")
        proc.kill()
        out, _ = proc.communicate()  # Get any output before termination
        timeout_msg = f"\n[ERROR] Command execution timed out after {COMMAND_TIMEOUT} seconds and was terminated."
        return {
            "exit_code": -1,
            "stdout": (out or "") + timeout_msg,
            "stderr": timeout_msg
        }


@ray.remote
def _read_file_parallel(rel_path: str, cached_content: Optional[str] = None) -> Dict[str, Any]:
    if cached_content is not None:
        return {"file": rel_path, "content": cached_content, "error": None, "size": len(cached_content), "cached": True}
    try:
        content = (SAMPLE_PROJECT_DIR / rel_path).read_text(encoding="utf-8")
        return {"file": rel_path, "content": content, "error": None, "size": len(content), "cached": False}
    except Exception as e:
        return {"file": rel_path, "content": None, "error": str(e), "size": 0, "cached": False}


def run_command(command: list[str]) -> Dict[str, Any]:
    logger.debug("run_command()")
    result = ray.get(_run_command.remote(command))
    logger.info(f"Exit code: {result['exit_code']}")
    return result


def read_files_parallel(file_paths: list, cached_contents: Optional[list] = None) -> list:
    if cached_contents is None:
        cached_contents = [None] * len(file_paths)
    
    futures = [_read_file_parallel.remote(f, c) for f, c in zip(file_paths, cached_contents)]
    return ray.get(futures)

