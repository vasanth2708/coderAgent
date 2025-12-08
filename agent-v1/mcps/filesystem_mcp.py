import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcps.logger_config import get_logger

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_PROJECT_DIR = BASE_DIR / "../sampleProject"

_file_cache: Dict[str, Dict[str, Any]] = {}


def clear_file_cache():
    """Clear the file cache - call this on session start to ensure fresh reads"""
    global _file_cache
    _file_cache.clear()
    logger.debug("File cache cleared")
logger = get_logger()


def get_file_mtime(rel_path: str) -> float:
    try:
        return (SAMPLE_PROJECT_DIR / rel_path).stat().st_mtime
    except Exception:
        return 0.0


def get_cached_file(rel_path: str) -> Optional[str]:
    if rel_path in _file_cache:
        cached = _file_cache[rel_path]
        current_mtime = get_file_mtime(rel_path)
        if cached["mtime"] == current_mtime:
            logger.debug(f"Using cached {rel_path}")
            return cached["content"]
        else:
            del _file_cache[rel_path]
    return None


def cache_file(rel_path: str, content: str, mtime: Optional[float] = None) -> None:
    if mtime is None:
        time.sleep(0.01)
        mtime = get_file_mtime(rel_path)
    _file_cache[rel_path] = {"content": content, "mtime": mtime}


def list_python_files() -> List[str]:
    logger.debug("list_python_files()")
    files = []
    directories_searched = set()
    for root, dirs, fs in os.walk(SAMPLE_PROJECT_DIR):
        rel_root = str(Path(root).relative_to(SAMPLE_PROJECT_DIR))
        if rel_root != '.':
            directories_searched.add(rel_root)
        for f in fs:
            if f.endswith(".py"):
                full = Path(root) / f
                rel_path = str(full.relative_to(SAMPLE_PROJECT_DIR))
                files.append(rel_path)
                logger.debug(f"Found: {rel_path}")
    result = sorted(files)
    logger.info(f"Total: {len(result)} Python files")
    if directories_searched:
        logger.debug(f"Searched directories: {sorted(directories_searched)}")
    return result


def read_file(rel_path: str) -> str:
    logger.debug(f"read_file(path='{rel_path}')")
    content = (SAMPLE_PROJECT_DIR / rel_path).read_text(encoding="utf-8")
    logger.debug(f"Read {len(content)} characters")
    return content


def write_file(rel_path: str, content: str) -> None:
    logger.debug(f"write_file(path='{rel_path}', content_length={len(content)})")
    path = SAMPLE_PROJECT_DIR / rel_path
    path.write_text(content, encoding="utf-8")
    logger.info(f"Wrote {len(content)} characters to {rel_path}")
    cache_file(rel_path, content)


def validate_edit_safety(filepath: str, edits: List[Dict[str, Any]]) -> Tuple[bool, str]:
    try:
        path = SAMPLE_PROJECT_DIR / filepath
        if not path.exists():
            return False, f"File {filepath} does not exist"
        
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        
        if len(edits) > 30:
            return False, f"Too many edits ({len(edits)}) - this might corrupt the file. Please make smaller changes."
        
        for edit in edits:
            line_num = edit.get("line", 0)
            if line_num < 1 or line_num > len(lines):
                return False, f"Invalid line number {line_num} (file has {len(lines)} lines)"
        
        return True, "Edits look safe"
    except Exception as e:
        return False, f"Validation error: {str(e)}"


def apply_line_edits(filepath: str, edits: List[Dict[str, Any]]) -> Tuple[bool, str, Optional[str]]:
    try:
        is_safe, safety_msg = validate_edit_safety(filepath, edits)
        if not is_safe:
            logger.warning(f"Validation failed: {safety_msg}")
            return False, safety_msg, None
        
        path = SAMPLE_PROJECT_DIR / filepath
        logger.info(f"Applying {len(edits)} edits to {filepath}")
        
        sorted_edits = sorted(edits, key=lambda x: x.get("line", 0), reverse=True)
        applied_count = 0
        skipped_count = 0
        
        for idx, edit in enumerate(sorted_edits, 1):
            logger.debug(f"Edit {idx}/{len(sorted_edits)}")
            
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)
            
            line_num = edit.get("line", 0) - 1
            old_code = edit.get("old", "")
            new_code = edit.get("new", "")
            
            logger.debug(f"Target line: {line_num + 1}")
            
            if line_num < 0 or line_num >= len(lines):
                logger.warning(f"Line {line_num + 1} out of range (file has {len(lines)} lines)")
                skipped_count += 1
                continue
            
            current_line = lines[line_num].rstrip('\n\r')
            logger.debug(f"Current: '{current_line[:80]}'")
            
            if not old_code or old_code.strip() == "":
                if new_code and new_code.strip():
                    lines.insert(line_num, new_code + '\n')
                    logger.debug(f"New: '{new_code[:80]}'")
                    logger.info(f"Inserted at line {line_num + 1}")
                    new_content = "".join(lines)
                    path.write_text(new_content, encoding="utf-8")
                    cache_file(filepath, new_content)
                    applied_count += 1
                continue
            
            if not new_code or new_code.strip() == "":
                old_stripped = old_code.strip()
                current_stripped = current_line.strip()
                logger.debug(f"Expected: '{old_stripped[:80]}'")
                if (old_stripped == current_stripped or     
                    old_stripped in current_line or
                    current_stripped in old_stripped):
                    lines.pop(line_num)
                    logger.info(f"Deleted line {line_num + 1}")
                    new_content = "".join(lines)
                    path.write_text(new_content, encoding="utf-8")
                    cache_file(filepath, new_content)
                    applied_count += 1
                else:
                    logger.warning("Mismatch - skipping deletion")
                    skipped_count += 1
                continue
            
            old_stripped = old_code.strip()
            current_stripped = current_line.strip()
            logger.debug(f"Expected: '{old_stripped[:80]}'")
            logger.debug(f"New: '{new_code[:80]}'")
            
            # More flexible matching: normalize whitespace, handle partial matches
            def normalize_code(code):
                """Normalize code for comparison"""
                return ' '.join(code.split())
            
            old_normalized = normalize_code(old_stripped)
            current_normalized = normalize_code(current_stripped)
            
            match_found = False
            if old_normalized == current_normalized:
                match_found = True
                logger.debug("Match: Exact (normalized)")
            elif old_normalized in current_normalized or current_normalized in old_normalized:
                match_found = True
                logger.debug("Match: Substring (normalized)")
            elif old_stripped == current_stripped:
                match_found = True
                logger.debug("Match: Exact (original)")
            elif old_stripped in current_line or current_stripped in old_stripped:
                match_found = True
                logger.debug("Match: Substring (original)")
            # Try matching just the significant parts (ignore comments, extra whitespace)
            elif old_normalized and len(old_normalized) > 10:
                # If old code is substantial, check if key parts match
                old_keywords = [w for w in old_normalized.split() if len(w) > 2]
                current_keywords = [w for w in current_normalized.split() if len(w) > 2]
                if old_keywords and all(kw in current_normalized for kw in old_keywords[:3]):
                    match_found = True
                    logger.debug("Match: Keyword-based")
            
            if match_found:
                if lines[line_num].endswith('\r\n'):
                    lines[line_num] = new_code + '\r\n'
                elif lines[line_num].endswith('\n'):
                    lines[line_num] = new_code + '\n'
                else:
                    lines[line_num] = new_code
                logger.info(f"Replaced line {line_num + 1}")
                new_content = "".join(lines)
                path.write_text(new_content, encoding="utf-8")
                cache_file(filepath, new_content)
                applied_count += 1
            else:
                logger.warning("No match - skipping replacement")
                skipped_count += 1
        
        message = f"Applied {applied_count}/{len(edits)} edits to {filepath}"
        if skipped_count > 0:
            message += f" ({skipped_count} skipped)"
        
        final_content = path.read_text(encoding="utf-8")
        cache_file(filepath, final_content)
        
        logger.info(f"Final: {message}")
        return True, message, final_content
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Error: {error_detail}")
        return False, f"Error applying edits to {filepath}: {str(e)}", None

