import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from mcps.logger_config import get_logger

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_FILE = BASE_DIR / ".coder_agent_memory.json"

logger = get_logger()


def compute_code_hash(file_contents: Dict[str, str]) -> str:
    sorted_files = sorted(file_contents.items())
    code_string = "\n".join([f"{path}:{content}" for path, content in sorted_files])
    return hashlib.sha256(code_string.encode('utf-8')).hexdigest()[:16]


def load_memory() -> Dict[str, Any]:
    if MEMORY_FILE.exists():
        try:
            mem = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            mem.setdefault("preferences", {})
            mem.setdefault("query_cache", {})
            mem.setdefault("memory_log", [])
            mem.setdefault("node_log", [])
            return mem
        except Exception as e:
            logger.warning(f"Error loading memory file: {e}, creating new one")
    return {
        "preferences": {},
        "query_cache": {},
        "memory_log": [],
        "node_log": []
    }


def save_memory(mem: Dict[str, Any], log_entry: Optional[Dict[str, Any]] = None) -> None:
    if log_entry:
        log_entry["timestamp"] = datetime.now().isoformat()
        mem.setdefault("memory_log", []).append(log_entry)
        if len(mem["memory_log"]) > 100:
            mem["memory_log"] = mem["memory_log"][-100:]
    
    MEMORY_FILE.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    if log_entry:
        logger.debug(f"Saved: {log_entry.get('action', 'update')} - {log_entry.get('description', '')}")


def get_cached_response(mem: Dict[str, Any], code_hash: str, query: str) -> Optional[str]:
    query_cache = mem.setdefault("query_cache", {})
    cache_key = f"{code_hash}:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:16]}"
    
    if cache_key in query_cache:
        cached = query_cache[cache_key]
        if cached.get("code_hash") == code_hash:
            logger.info(f"Using cached response for query (code unchanged, cache_size: {len(query_cache)})")
            return cached.get("response")
        else:
            del query_cache[cache_key]
            save_memory(mem, {
                "action": "invalidate_cache",
                "description": f"Removed stale cache entry (code_hash changed)",
                "cache_key": cache_key
            })
            logger.info("Cache entry invalidated (code changed)")
    return None


def cache_response(mem: Dict[str, Any], code_hash: str, query: str, response: str) -> None:
    query_cache = mem.setdefault("query_cache", {})
    cache_key = f"{code_hash}:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:16]}"
    
    query_cache[cache_key] = {
        "code_hash": code_hash,
        "query": query,
        "response": response,
        "cached_at": datetime.now().isoformat()
    }
    
    if len(query_cache) > 500:
        keys_to_remove = list(query_cache.keys())[:100]
        for key in keys_to_remove:
            del query_cache[key]
        logger.info(f"Cache size limit reached, removed {len(keys_to_remove)} oldest entries")
    
    save_memory(mem, {
        "action": "cache_response",
        "description": f"Cached response for query (code_hash: {code_hash[:8]}..., cache_size: {len(query_cache)})",
        "cache_key": cache_key
    })
    logger.debug(f"Cache updated in memory and persisted to file ({len(query_cache)} entries)")


def update_preferences_from_text(mem: Dict[str, Any], text: str) -> bool:
    """Dynamically extract preferences from user text using LLM"""
    from langchain_core.messages import HumanMessage, SystemMessage
    from mcps.llm_config import get_llm
    
    lower = text.lower()
    prefs = mem.setdefault("preferences", {})
    
    
    # Use LLM to dynamically extract preferences from natural language
    sys_msg = SystemMessage(content=(
        "Extract coding preferences from the user's text. Return ONLY a JSON object with boolean values.\n"
        "Possible preferences:\n"
        "- write_comments: true if user wants comments added when editing code, false if not\n"
        "- add_docstrings: true if user wants docstrings added to functions/classes, false if not\n"
        "- (you can infer other preferences based on context)\n\n"
        "Return JSON only, no explanations. Example: {\"write_comments\": true, \"add_docstrings\": false}\n"
        "If no preferences found, return empty object: {}"
    ))
    
    try:
        llm = get_llm()
        msg = llm.invoke([sys_msg, HumanMessage(content=text)])
        
        response = msg.content.strip()
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        extracted_prefs = json.loads(response)
        
        if extracted_prefs and isinstance(extracted_prefs, dict):
            changed = False
            for key, value in extracted_prefs.items():
                if isinstance(value, bool) and prefs.get(key) != value:
                    prefs[key] = value
                    changed = True
                    logger.info(f"Preference updated: {key} = {value}")
            
            if changed:
                save_memory(mem, {
                    "action": "update_preferences",
                    "description": f"Updated preferences: {prefs}"
                })
                logger.info(f"Preferences updated: {prefs}")
            return changed
    except Exception as e:
        logger.warning(f"Failed to extract preferences dynamically: {e}")
        return False
    
    return False

