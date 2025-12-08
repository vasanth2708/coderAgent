import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import ray

from mcps.logger_config import get_logger

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_PROJECT_DIR = BASE_DIR / "../sampleProject"

logger = get_logger()


@ray.remote
def _run_pytest() -> Dict[str, str]:
    # Run pytest with verbose output to capture all test results
    proc = subprocess.Popen(
        ["pytest", "-v", "--tb=short"],
        cwd=SAMPLE_PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        text=True,
    )
    out, _ = proc.communicate()
    return {"exit_code": proc.returncode, "stdout": out, "stderr": ""}


@ray.remote
def _read_file_parallel(rel_path: str, cached_content: Optional[str] = None) -> Dict[str, Any]:
    if cached_content is not None:
        return {"file": rel_path, "content": cached_content, "error": None, "size": len(cached_content), "cached": True}
    try:
        content = (SAMPLE_PROJECT_DIR / rel_path).read_text(encoding="utf-8")
        return {"file": rel_path, "content": content, "error": None, "size": len(content), "cached": False}
    except Exception as e:
        return {"file": rel_path, "content": None, "error": str(e), "size": 0, "cached": False}


def run_pytest() -> Dict[str, Any]:
    logger.debug("run_tests()")
    result = ray.get(_run_pytest.remote())
    logger.info(f"Exit code: {result['exit_code']}")
    return result


def read_files_parallel(file_paths: list, cached_contents: Optional[list] = None) -> list:
    if cached_contents is None:
        cached_contents = [None] * len(file_paths)
    
    futures = [_read_file_parallel.remote(f, c) for f, c in zip(file_paths, cached_contents)]
    return ray.get(futures)

