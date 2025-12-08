import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import ray
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field

# =====================
# CONFIG
# =====================

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_PROJECT_DIR = BASE_DIR / "../sampleProject"
MEMORY_FILE = BASE_DIR / ".coder_agent_memory.json"

llm = ChatOpenAI(
    model="deepseek-chat",
    temperature=0,
    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    openai_api_base="https://api.deepseek.com/v1",
)

if not ray.is_initialized():
    ray.init(
        ignore_reinit_error=True,
        include_dashboard=False,
        log_to_driver=False,
    )

# =====================
# FILE CACHE
# =====================

_file_cache: Dict[str, Dict[str, Any]] = {}  # {filepath: {content: str, mtime: float}}

def get_file_mtime(rel_path: str) -> float:
    """Get file modification time"""
    try:
        return (SAMPLE_PROJECT_DIR / rel_path).stat().st_mtime
    except Exception:
        return 0.0

def get_cached_file(rel_path: str) -> Optional[str]:
    """Get file from cache if it exists and is up to date"""
    if rel_path in _file_cache:
        cached = _file_cache[rel_path]
        current_mtime = get_file_mtime(rel_path)
        if cached["mtime"] == current_mtime:
            print(f"  [CACHE] Using cached {rel_path}")
            return cached["content"]
        else:
            # File was modified, remove from cache
            del _file_cache[rel_path]
    return None

def cache_file(rel_path: str, content: str, mtime: Optional[float] = None) -> None:
    """Cache file content with modification time"""
    if mtime is None:
        # Small delay to ensure file system has updated mtime after file write
        time.sleep(0.01)  # 10ms delay to ensure mtime is updated
        mtime = get_file_mtime(rel_path)
    _file_cache[rel_path] = {"content": content, "mtime": mtime}

# =====================
# MEMORY
# =====================

def compute_code_hash(file_contents: Dict[str, str]) -> str:
    """Compute a hash of the current code state"""
    # Sort files for consistent hashing
    sorted_files = sorted(file_contents.items())
    # Create a string representation of all file contents
    code_string = "\n".join([f"{path}:{content}" for path, content in sorted_files])
    # Compute SHA256 hash
    return hashlib.sha256(code_string.encode('utf-8')).hexdigest()[:16]


def load_memory() -> Dict[str, Any]:
    """Load memory from file, ensuring all required structures exist"""
    if MEMORY_FILE.exists():
        try:
            mem = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            # Ensure all required structures exist
            mem.setdefault("preferences", {})
            mem.setdefault("query_cache", {})
            mem.setdefault("memory_log", [])
            mem.setdefault("node_log", [])
            return mem
        except Exception as e:
            print(f"  [MEMORY] Error loading memory file: {e}, creating new one")
    return {
        "preferences": {},
        "query_cache": {},
        "memory_log": [],
        "node_log": []
    }


def save_memory(mem: Dict[str, Any], log_entry: Optional[Dict[str, Any]] = None) -> None:
    """Save memory to file and optionally log the save operation"""
    if log_entry:
        log_entry["timestamp"] = datetime.now().isoformat()
        mem.setdefault("memory_log", []).append(log_entry)
        # Keep only last 100 log entries
        if len(mem["memory_log"]) > 100:
            mem["memory_log"] = mem["memory_log"][-100:]
    
    MEMORY_FILE.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    if log_entry:
        print(f"  [MEMORY] Saved: {log_entry.get('action', 'update')} - {log_entry.get('description', '')}")


def log_node_execution(mem: Dict[str, Any], node_name: str, input_summary: Dict[str, Any], 
                       output_summary: Dict[str, Any], duration: float) -> None:
    """Log a node execution to memory"""
    node_log = mem.setdefault("node_log", [])
    
    log_entry = {
        "node_name": node_name,
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": round(duration, 3),
        "input": input_summary,
        "output": output_summary
    }
    
    node_log.append(log_entry)
    
    # Keep only last 1000 node executions
    if len(node_log) > 1000:
        node_log[:] = node_log[-1000:]
    
    # Save to file periodically (every 10 executions) or immediately for important nodes
    if len(node_log) % 10 == 0 or node_name in ["edit", "read", "run_tests"]:
        save_memory(mem)
        print(f"  [NODE_LOG] Logged {node_name} execution (total: {len(node_log)} entries)")


def get_cached_response(mem: Dict[str, Any], code_hash: str, query: str) -> Optional[str]:
    """Get cached response if code hash matches and query exists.
    Ensures cache is loaded from file and handles stale entries.
    """
    # Ensure query_cache exists in memory
    query_cache = mem.setdefault("query_cache", {})
    cache_key = f"{code_hash}:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:16]}"
    
    if cache_key in query_cache:
        cached = query_cache[cache_key]
        # Verify code hash still matches (code hasn't changed)
        if cached.get("code_hash") == code_hash:
            print(f"  [MEMORY] Using cached response for query (code unchanged, cache_size: {len(query_cache)})")
            return cached.get("response")
        else:
            # Code has changed, remove stale cache entry
            del query_cache[cache_key]
            save_memory(mem, {
                "action": "invalidate_cache",
                "description": f"Removed stale cache entry (code_hash changed)",
                "cache_key": cache_key
            })
            print(f"  [MEMORY] Cache entry invalidated (code changed)")
    return None


def cache_response(mem: Dict[str, Any], code_hash: str, query: str, response: str) -> None:
    """Cache a query response with code hash and immediately persist to file"""
    query_cache = mem.setdefault("query_cache", {})
    cache_key = f"{code_hash}:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:16]}"
    
    query_cache[cache_key] = {
        "code_hash": code_hash,
        "query": query,
        "response": response,
        "cached_at": datetime.now().isoformat()
    }
    
    # Limit cache size to 500 entries
    if len(query_cache) > 500:
        # Remove oldest entries (simple: remove first 100)
        keys_to_remove = list(query_cache.keys())[:100]
        for key in keys_to_remove:
            del query_cache[key]
        print(f"  [MEMORY] Cache size limit reached, removed {len(keys_to_remove)} oldest entries")
    
    # Immediately persist to file
    save_memory(mem, {
        "action": "cache_response",
        "description": f"Cached response for query (code_hash: {code_hash[:8]}..., cache_size: {len(query_cache)})",
        "cache_key": cache_key
    })
    print(f"  [MEMORY] Cache updated in memory and persisted to file ({len(query_cache)} entries)")


def update_preferences_from_text(mem: Dict[str, Any], text: str) -> bool:
    changed = False
    lower = text.lower()
    prefs = mem.setdefault("preferences", {})
    if "always add docstring" in lower:
        prefs["add_docstrings"] = True
        changed = True
    if "never add docstring" in lower:
        prefs["add_docstrings"] = False
        changed = True
    if changed:
        save_memory(mem, {
            "action": "update_preferences",
            "description": f"Updated preferences: {prefs}"
        })
    return changed


# =====================
# RAY EXECUTION
# =====================

@ray.remote
def _run_pytest() -> Dict[str, str]:
    proc = subprocess.Popen(
        ["pytest", "-q"],
        cwd=SAMPLE_PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = proc.communicate()
    return {"exit_code": proc.returncode, "stdout": out, "stderr": err}


@ray.remote
def _read_file_parallel(rel_path: str, cached_content: Optional[str] = None) -> Dict[str, Any]:
    """Read a file in parallel using Ray, using cache if provided"""
    if cached_content is not None:
        return {"file": rel_path, "content": cached_content, "error": None, "size": len(cached_content), "cached": True}
    try:
        content = (SAMPLE_PROJECT_DIR / rel_path).read_text(encoding="utf-8")
        return {"file": rel_path, "content": content, "error": None, "size": len(content), "cached": False}
    except Exception as e:
        return {"file": rel_path, "content": None, "error": str(e), "size": 0, "cached": False}


def run_tests() -> Dict[str, Any]:
    print("[TOOL] run_tests()")
    result = ray.get(_run_pytest.remote())
    print(f"  → Exit code: {result['exit_code']}")
    return result


# =====================
# FILE UTILITIES
# =====================

def list_python_files() -> List[str]:
    print("[TOOL] list_python_files()")
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
                print(f"  → Found: {rel_path}")
    result = sorted(files)
    print(f"  → Total: {len(result)} Python files")
    if directories_searched:
        print(f"  → Searched directories: {sorted(directories_searched)}")
    return result


def read_file(rel_path: str) -> str:
    print(f"[TOOL] read_file(path='{rel_path}')")
    content = (SAMPLE_PROJECT_DIR / rel_path).read_text(encoding="utf-8")
    print(f"  → Read {len(content)} characters")
    return content


def write_file(rel_path: str, content: str) -> None:
    print(f"[TOOL] write_file(path='{rel_path}', content_length={len(content)})")
    path = SAMPLE_PROJECT_DIR / rel_path
    path.write_text(content, encoding="utf-8")
    print(f"  → Wrote {len(content)} characters")
    # Update cache
    cache_file(rel_path, content)

def validate_edit_safety(filepath: str, edits: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Validate that edits won't corrupt the file"""
    try:
        path = SAMPLE_PROJECT_DIR / filepath
        if not path.exists():
            return False, f"File {filepath} does not exist"
        
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        
        # Check for reasonable edit counts
        if len(edits) > 30:
            return False, f"Too many edits ({len(edits)}) - this might corrupt the file. Please make smaller changes."
        
        # Check line numbers are valid
        for edit in edits:
            line_num = edit.get("line", 0)
            if line_num < 1 or line_num > len(lines):
                return False, f"Invalid line number {line_num} (file has {len(lines)} lines)"
        
        return True, "Edits look safe"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def apply_edits_to_file(filepath: str, edits: List[Dict[str, Any]]) -> Tuple[bool, str, Optional[str]]:
    """Apply edits to a file ONE BY ONE with file reload after each edit.
    Returns: (success, message, final_content)
    """
    try:
        # First validate the edits
        is_safe, safety_msg = validate_edit_safety(filepath, edits)
        if not is_safe:
            print(f"  ⚠ {safety_msg}")
            return False, safety_msg
        
        path = SAMPLE_PROJECT_DIR / filepath
        
        print(f"  → Applying {len(edits)} edits ONE BY ONE")
        
        # Sort edits by line number (descending) to minimize line number shifts
        sorted_edits = sorted(edits, key=lambda x: x.get("line", 0), reverse=True)
        
        applied_count = 0
        skipped_count = 0
        
        # Apply each edit one by one, reloading the file each time
        for idx, edit in enumerate(sorted_edits, 1):
            print(f"\n  [Edit {idx}/{len(sorted_edits)}]")
            
            # Reload file for each edit
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)
            
            line_num = edit.get("line", 0) - 1
            old_code = edit.get("old", "")
            new_code = edit.get("new", "")
            
            print(f"  → Target line: {line_num + 1}")
            
            if line_num < 0 or line_num >= len(lines):
                print(f"  ⚠ Line {line_num + 1} out of range (file has {len(lines)} lines)")
                skipped_count += 1
                continue
            
            current_line = lines[line_num].rstrip('\n\r')
            print(f"  → Current: '{current_line[:80]}'")
            
            # Insertion
            if not old_code or old_code.strip() == "":
                if new_code and new_code.strip():
                    lines.insert(line_num, new_code + '\n')
                    print(f"  → New: '{new_code[:80]}'")
                    print(f"  ✓ Inserted at line {line_num + 1}")
                    
                    # Write immediately
                    new_content = "".join(lines)
                    path.write_text(new_content, encoding="utf-8")
                    cache_file(filepath, new_content)
                    applied_count += 1
                continue
            
            # Deletion
            if not new_code or new_code.strip() == "":
                old_stripped = old_code.strip()
                current_stripped = current_line.strip()
                
                print(f"  → Expected: '{old_stripped[:80]}'")
                
                # Be more lenient for deletions
                if (old_stripped == current_stripped or 
                    old_stripped in current_line or
                    current_stripped in old_stripped):
                    lines.pop(line_num)
                    print(f"  ✓ Deleted line {line_num + 1}")
                    
                    # Write immediately
                    new_content = "".join(lines)
                    path.write_text(new_content, encoding="utf-8")
                    cache_file(filepath, new_content)
                    applied_count += 1
                else:
                    print(f"  ⚠ Mismatch - skipping deletion")
                    skipped_count += 1
                continue
            
            # Replacement
            old_stripped = old_code.strip()
            current_stripped = current_line.strip()
            
            print(f"  → Expected: '{old_stripped[:80]}'")
            print(f"  → New: '{new_code[:80]}'")
            
            match_found = False
            if old_stripped == current_stripped:
                match_found = True
                print(f"  → Match: Exact")
            elif old_stripped in current_line or current_stripped in old_stripped:
                match_found = True
                print(f"  → Match: Substring")
            elif old_stripped.replace(' ', '') == current_stripped.replace(' ', ''):
                match_found = True
                print(f"  → Match: Whitespace-normalized")
            
            if match_found:
                # Preserve line ending
                if lines[line_num].endswith('\r\n'):
                    lines[line_num] = new_code + '\r\n'
                elif lines[line_num].endswith('\n'):
                    lines[line_num] = new_code + '\n'
                else:
                    lines[line_num] = new_code
                
                print(f"  ✓ Replaced line {line_num + 1}")
                
                # Write immediately
                new_content = "".join(lines)
                path.write_text(new_content, encoding="utf-8")
                cache_file(filepath, new_content)
                applied_count += 1
            else:
                print(f"  ⚠ No match - skipping replacement")
                skipped_count += 1
        
        message = f"Applied {applied_count}/{len(edits)} edits to {filepath}"
        if skipped_count > 0:
            message += f" ({skipped_count} skipped)"
        
        # Read final content to return
        final_content = path.read_text(encoding="utf-8")
        # Update cache with final content
        cache_file(filepath, final_content)
        
        print(f"\n  → Final: {message}")
        return True, message, final_content
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"  ⚠ Error: {error_detail}")
        return False, f"Error applying edits to {filepath}: {str(e)}", None


# =====================
# STATE
# =====================

class AgentState(BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    intent: Optional[Literal["read", "edit", "run_tests", "profile"]] = None
    target_files: List[str] = Field(default_factory=list)
    pending_edits: Dict[str, Any] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=load_memory)
    done: bool = False
    session_context: Dict[str, Any] = Field(default_factory=lambda: {
        "read_files": [],  # Files already read in this session
        "file_contents": {},  # Cached file contents from session
        "conversation_history": []  # Previous Q&A pairs
    })


def last_user_text(state: AgentState) -> str:
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


# =====================
# GRAPH NODES
# =====================

def route_node(state: AgentState) -> AgentState:
    print(f"[NODE] route_node()")
    start_time = time.time()
    text = last_user_text(state)
    input_summary = {
        "user_text": text[:100] if text else "",
        "intent": state.intent,
        "messages_count": len(state.messages)
    }
    if update_preferences_from_text(state.memory, text):
        state.intent = "profile"
        print(f"  → Intent: profile (from preferences)")
        # Log node execution
        duration = time.time() - start_time
        output_summary = {"intent": state.intent, "done": False}
        log_node_execution(state.memory, "route", input_summary, output_summary, duration)
        return state

    sys = SystemMessage(
        content=(
            "Choose intent: read | edit | run_tests | profile.\n"
            "Return only the intent word."
        )
    )
    print(f"[LLM] Calling LLM to determine intent...")
    print(f"  Input: {text[:100]}...")
    msg = llm.invoke([sys, HumanMessage(content=text)])
    print(f"  Response: {msg.content}")
    out = msg.content.lower()

    if "test" in out:
        state.intent = "run_tests"
    elif "edit" in out or "fix" in out or "add" in out:
        state.intent = "edit"
    elif "profile" in out:
        state.intent = "profile"
    else:
        state.intent = "read"
    
    print(f"  → Intent: {state.intent}")
    
    # Log node execution
    duration = time.time() - start_time
    output_summary = {
        "intent": state.intent,
        "done": state.done
    }
    log_node_execution(state.memory, "route", input_summary, output_summary, duration)

    return state


def profile_node(state: AgentState) -> AgentState:
    print(f"[NODE] profile_node()")
    start_time = time.time()
    prefs = state.memory.get("preferences", {})
    print(f"  → Preferences: {prefs}")
    state.messages.append(AIMessage(content=f"Saved preferences: {prefs}"))
    state.done = True
    
    # Log node execution
    duration = time.time() - start_time
    log_node_execution(state.memory, "profile", {"preferences": prefs}, {"done": True}, duration)
    
    return state


def plan_read_node(state: AgentState) -> AgentState:
    print(f"[NODE] plan_read_node()")
    start_time = time.time()
    files = list_python_files()
    input_summary = {
        "already_read_count": len(state.session_context.get("read_files", [])),
        "available_files_count": 0
    }
    
    # Check what files were already read in this session
    already_read = state.session_context.get("read_files", [])
    if already_read:
        print(f"  → Previously read in session: {len(already_read)} files")
    
    # Use LLM to select files, but include context about what's already been read
    sys = SystemMessage(
        content=(
            "Select which files to read. Return JSON list.\n"
            f"Files already read in this session: {already_read}\n"
            "You can select new files or reuse already read ones."
        )
    )
    print(f"[LLM] Calling LLM to select files...")
    print(f"  Available files: {len(files)} files")
    print(f"  Already read: {len(already_read)} files")
    
    context_msg = f"Available: {json.dumps(files)}\nAlready read: {json.dumps(already_read)}"
    msg = llm.invoke([
        sys,
        HumanMessage(content=context_msg)
    ])
    print(f"  Response: {msg.content}")
    try:
        # Extract JSON from markdown code blocks if present
        content = msg.content.strip()
        # Remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            # Try to extract from generic code block
            parts = content.split("```")
            if len(parts) >= 3:
                # Take the content between first and second ```
                content = parts[1].strip()
                # If it starts with "json", remove that
                if content.startswith("json"):
                    content = content[4:].strip()
        
        print(f"  → Extracted JSON: {content[:200]}...")
        selected = json.loads(content)
        
        # Ensure it's a list
        if not isinstance(selected, list):
            selected = [selected]
        
        # Validate that all selected files exist
        valid_files = [f for f in selected if f in files]
        if not valid_files:
            print(f"  ⚠ No valid files found in selection, using all files")
            state.target_files = files
        else:
            state.target_files = valid_files
            print(f"  → Selected {len(state.target_files)} files: {state.target_files}")
    except Exception as e:
        print(f"  ⚠ Failed to parse JSON: {e}")
        print(f"  → Using all {len(files)} files instead")
        state.target_files = files
    
    # Log node execution
    duration = time.time() - start_time
    input_summary["available_files_count"] = len(files)
    output_summary = {
        "target_files_count": len(state.target_files),
        "target_files": state.target_files[:5]  # Log first 5 files
    }
    log_node_execution(state.memory, "plan_read", input_summary, output_summary, duration)
    
    return state


def read_node(state: AgentState) -> AgentState:
    print(f"[NODE] read_node()")
    node_start_time = time.time()
    print(f"  → Reading {len(state.target_files)} files in parallel...")
    
    # Check session context first, then file cache
    user_question = last_user_text(state)
    input_summary = {
        "target_files_count": len(state.target_files),
        "target_files": state.target_files[:3],  # Log first 3
        "user_question": user_question[:100] if user_question else ""
    }
    cached_count = 0
    session_cached = 0
    files_to_read = []
    
    for f in state.target_files:
        # First check session context
        if f in state.session_context.get("file_contents", {}):
            session_cached += 1
            cached_content = state.session_context["file_contents"][f]
            files_to_read.append((f, cached_content))
            print(f"  [SESSION] Using session-cached {f}")
        # Then check file cache
        elif get_cached_file(f):
            cached_content = get_cached_file(f)
            cached_count += 1
            files_to_read.append((f, cached_content))
        else:
            files_to_read.append((f, None))
    
    if session_cached > 0:
        print(f"  → {session_cached}/{len(state.target_files)} files from session cache")
    if cached_count > 0:
        print(f"  → {cached_count}/{len(state.target_files)} files from file cache")
    
    # Parallel file reading using Ray (only for files not in session)
    files_to_fetch = [(f, cached) for f, cached in files_to_read if cached is None]
    if files_to_fetch:
        start_time = time.time()
        futures = [_read_file_parallel.remote(f, None) for f, _ in files_to_fetch]
        print(f"  → Launched {len(futures)} parallel read tasks")
        results = ray.get(futures)
        read_time = time.time() - start_time
        print(f"  → Parallel read completed in {read_time:.3f}s")
    else:
        results = []
        print(f"  → All files from cache, no disk I/O needed")
    
    # Process results and update both caches
    content = []
    total_size = 0
    file_contents_map = {}
    
    # Process files that were already cached (session or file cache)
    for f, cached_content in files_to_read:
        if cached_content is not None and f not in [r["file"] for r in results]:
            content.append(f"# {f}\n{cached_content}")
            total_size += len(cached_content)
            file_contents_map[f] = cached_content
            print(f"  ✓ Cached {f} ({len(cached_content)} chars)")
    
    # Process newly read files
    for result in results:
        if result["error"]:
            print(f"  ⚠ Error reading {result['file']}: {result['error']}")
            content.append(f"# {result['file']}\nERROR: {result['error']}")
        else:
            content.append(f"# {result['file']}\n{result['content']}")
            total_size += result['size']
            file_contents_map[result['file']] = result['content']
            # Update both caches
            cache_file(result['file'], result['content'])
            if not result.get("cached", False):
                print(f"  ✓ Read {result['file']} ({result['size']} chars)")
            else:
                print(f"  ✓ Cached {result['file']} ({result['size']} chars)")
    
    # Update session context with all read files
    state.session_context["read_files"].extend(state.target_files)
    state.session_context["read_files"] = list(set(state.session_context["read_files"]))  # Remove duplicates
    state.session_context["file_contents"].update(file_contents_map)
    
    print(f"  → Total content: {total_size} characters from {len(content)} files")
    print(f"  → Session now has {len(state.session_context['read_files'])} files in context")
    
    # Check memory cache for this query
    code_hash = compute_code_hash(file_contents_map)
    print(f"  [MEMORY] Code hash: {code_hash[:16]}...")
    
    cached_response = get_cached_response(state.memory, code_hash, user_question)
    if cached_response:
        msg = AIMessage(content=cached_response)
        print(f"  → Using cached response ({len(cached_response)} characters)")
    else:
        # Arbitration agent - answers only the specific user question, with conversation history
        print(f"[ARBITRATION] Processing retrieved content...")
        arbitration_start = time.time()
        
        # Include conversation history for context
        history = state.session_context.get("conversation_history", [])
        history_context = ""
        if history:
            history_context = "\n\nPrevious conversation:\n" + "\n".join([f"Q: {h['q']}\nA: {h['a'][:200]}..." for h in history[-3:]])
        
        arbitration_prompt = (
            f"Answer ONLY the user's specific question: '{user_question}'\n\n"
            "Use the provided code files to answer the question directly and concisely. "
            "Do not provide a full codebase explanation unless specifically asked. "
            "Focus on answering what was asked."
            f"{history_context}"
        )
        
        print(f"[LLM] Calling LLM (arbitration agent) to answer question...")
        msg = llm.invoke([
            SystemMessage(content=arbitration_prompt),
            HumanMessage(content=f"User question: {user_question}\n\nCode files:\n\n" + "\n\n".join(content))
        ])
        arbitration_time = time.time() - arbitration_start
        print(f"  → Arbitration completed in {arbitration_time:.3f}s")
        print(f"  → Response: {len(msg.content)} characters")
        
        # Cache the response
        cache_response(state.memory, code_hash, user_question, msg.content)
    
    # Store in conversation history
    state.session_context["conversation_history"].append({
        "q": user_question,
        "a": msg.content
    })
    # Keep only last 10 conversations
    if len(state.session_context["conversation_history"]) > 10:
        state.session_context["conversation_history"] = state.session_context["conversation_history"][-10:]
    
    state.messages.append(AIMessage(content=msg.content))
    state.done = True
    
    # Log node execution
    duration = time.time() - node_start_time
    output_summary = {
        "files_read_count": len(state.target_files),
        "total_content_size": sum(len(state.session_context.get("file_contents", {}).get(f, "")) for f in state.target_files),
        "used_cache": cached_response is not None,
        "response_length": len(msg.content)
    }
    log_node_execution(state.memory, "read", input_summary, output_summary, duration)
    
    return state


def edit_node(state: AgentState) -> AgentState:
    print(f"[NODE] edit_node()")
    node_start_time = time.time()
    user_request = last_user_text(state)
    input_summary = {
        "user_request": user_request[:100] if user_request else "",
        "session_files_count": len(state.session_context.get("file_contents", {}))
    }
    
    # Use session context to get previously read files
    session_files = state.session_context.get("file_contents", {})
    if not session_files:
        # If no files in session, read all Python files
        print(f"  → No files in session, reading all Python files...")
        all_files = list_python_files()
        state.target_files = all_files
        # Trigger a read first
        state = read_node(state)
        session_files = state.session_context.get("file_contents", {})
    
    print(f"  → Using {len(session_files)} files from session context")
    
    # Determine which files need to be edited based on user request
    files_to_edit = []
    for filepath in session_files.keys():
        # Simple heuristic: if user mentions a file or it's likely relevant
        if any(part in user_request.lower() for part in filepath.lower().split('/')):
            files_to_edit.append(filepath)
    
    # If no specific files mentioned, use all session files
    if not files_to_edit:
        files_to_edit = list(session_files.keys())[:5]  # Limit to 5 files
    
    print(f"  → Editing {len(files_to_edit)} files: {files_to_edit}")
    
    # Create edit prompt with file contents - add line numbers for clarity
    file_contents = []
    for f in files_to_edit:
        if f in session_files:
            # Add line numbers to help LLM
            lines = session_files[f].splitlines()
            numbered_lines = "\n".join([f"{i+1:4d} | {line}" for i, line in enumerate(lines)])
            file_contents.append(f"# {f}\n{numbered_lines}")
    
    # Get test results if available for context
    test_context = ""
    if "test" in user_request.lower() or "fix" in user_request.lower():
        test_result = run_tests()
        if test_result["exit_code"] != 0:
            test_context = f"\n\nTest failures:\n{test_result['stdout']}\n{test_result['stderr']}\n"
    
    edit_prompt = (
        f"User request: {user_request}\n\n"
        f"{test_context}"
        "Analyze the code files below (with line numbers) and provide the necessary edits.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Line numbers are shown at the start of each line (e.g., '  1 | code')\n"
        "2. Use these EXACT line numbers in your edits\n"
        "3. Return ONLY a JSON array, NO explanations, NO markdown\n\n"
        "JSON format:\n"
        '[{"file": "path/to/file.py", "edits": [{"line": 10, "old": "exact old code", "new": "new code"}]}]\n\n'
        "Rules:\n"
        "- 'line': The exact line number from the file (count carefully!)\n"
        "- 'old': Copy the EXACT code from that line (can be partial for matching)\n"
        "- 'new': The complete replacement code\n"
        "- For insertions: set 'old' to empty string\n"
        "- For deletions: set 'new' to empty string\n"
        "- Be precise with line numbers - they are the primary matching mechanism\n"
    )
    
    print(f"[LLM] Calling LLM to generate edits...")
    msg = llm.invoke([
        SystemMessage(content=edit_prompt),
        HumanMessage(content="\n\n".join(file_contents))
    ])
    
    print(f"  → Generated edit plan")
    print(f"  → LLM Response length: {len(msg.content)} characters")
    
    # Try to parse the JSON response
    edits_data = []
    try:
        # Try to extract JSON from the response
        content = msg.content.strip()
        # Remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        print(f"  → Attempting to parse JSON: {content[:200]}...")
        edits_data = json.loads(content)
        if not isinstance(edits_data, list):
            edits_data = [edits_data]
        print(f"  → Successfully parsed {len(edits_data)} edit items")
    except Exception as e:
        print(f"  ⚠ Failed to parse edits JSON: {e}")
        print(f"  → Raw content: {msg.content[:500]}")
        # Fallback: create a simple edit structure
        edits_data = [{"file": f, "edits": []} for f in files_to_edit]
    
    # Store edits in proper format
    state.pending_edits = {
        "edits": edits_data,
        "files": files_to_edit,
        "plan": msg.content
    }
    
    # Show edit plan with details
    edit_summary = f"Edit plan generated for {len(files_to_edit)} files:\n\n"
    total_edits = 0
    for edit_item in edits_data:
        if isinstance(edit_item, dict) and "file" in edit_item:
            edit_summary += f"File: {edit_item['file']}\n"
            if "edits" in edit_item:
                num_edits = len(edit_item['edits'])
                total_edits += num_edits
                edit_summary += f"  {num_edits} edit(s) planned\n"
                # Show first few edits as preview
                for i, edit in enumerate(edit_item['edits'][:3]):
                    line = edit.get('line', '?')
                    edit_summary += f"    - Line {line}\n"
    
    edit_summary += f"\nTotal: {total_edits} edit(s) across {len(files_to_edit)} file(s)"
    edit_summary += "\n\nType 'approve' to apply changes, or ask for modifications."
    
    state.messages.append(AIMessage(content=edit_summary))
    state.done = True
    
    # Log node execution
    duration = time.time() - node_start_time
    output_summary = {
        "files_to_edit_count": len(files_to_edit),
        "total_edits_planned": total_edits,
        "has_pending_edits": bool(state.pending_edits)
    }
    log_node_execution(state.memory, "edit", input_summary, output_summary, duration)
    
    return state


def run_tests_node(state: AgentState) -> AgentState:
    print(f"[NODE] run_tests_node()")
    node_start_time = time.time()
    result = run_tests()
    input_summary = {}
    if result["exit_code"] == 0:
        print(f"  → All tests passed")
        state.messages.append(AIMessage(content="✅ All tests passed."))
    else:
        print(f"  → Tests failed")
        state.messages.append(
            AIMessage(content=f"❌ Tests failed:\n\n{result['stdout']}\n{result['stderr']}")
        )
    state.done = True
    
    # Log node execution
    duration = time.time() - node_start_time
    output_summary = {
        "exit_code": result["exit_code"],
        "tests_passed": result["exit_code"] == 0,
        "stdout_length": len(result.get("stdout", "")),
        "stderr_length": len(result.get("stderr", ""))
    }
    log_node_execution(state.memory, "run_tests", input_summary, output_summary, duration)
    
    return state


# =====================
# GRAPH BUILD
# =====================

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("route", route_node)
    graph.add_node("profile", profile_node)
    graph.add_node("plan_read", plan_read_node)
    graph.add_node("read", read_node)
    graph.add_node("edit", edit_node)
    graph.add_node("run_tests", run_tests_node)

    graph.add_edge(START, "route")

    graph.add_conditional_edges(
        "route",
        lambda s: s.intent,
        {
            "profile": "profile",
            "read": "plan_read",
            "edit": "edit",
            "run_tests": "run_tests",
        },
    )

    graph.add_edge("plan_read", "read")
    graph.add_edge("profile", END)
    graph.add_edge("read", END)
    graph.add_edge("edit", END)
    graph.add_edge("run_tests", END)

    return graph.compile()


# =====================
# CLI
# =====================

def main():
    app = build_graph()
    state = AgentState()
    print("AI Coding Agent (LangGraph + DeepSeek + Ray)")
    print("Type 'exit' or 'quit' to stop.\n")
    print("Session context will be maintained across requests.\n")
    
    # Show memory/cache status on startup
    cache_size = len(state.memory.get("query_cache", {}))
    node_log_size = len(state.memory.get("node_log", []))
    if cache_size > 0:
        print(f"[MEMORY] Loaded {cache_size} cached query responses from file")
        print(f"[MEMORY] Cache will be reused when code hasn't changed")
    else:
        print(f"[MEMORY] No cached responses found. Cache will be built as queries are made.")
    
    if node_log_size > 0:
        print(f"[MEMORY] Loaded {node_log_size} node execution logs from file")
        # Show last 5 node executions
        recent_nodes = state.memory.get("node_log", [])[-5:]
        print(f"[MEMORY] Recent node executions:")
        for log_entry in recent_nodes:
            node_name = log_entry.get("node_name", "unknown")
            timestamp = log_entry.get("timestamp", "")[:19]  # Just date and time
            duration = log_entry.get("duration_seconds", 0)
            print(f"  - {node_name} ({timestamp}, {duration:.3f}s)")
    print()

    while True:
        user_input = input("You> ")
        if user_input.lower() in {"exit", "quit"}:
            break
        
        # Handle "approve" command for applying edits
        if user_input.lower() == "approve" and state.pending_edits:
            print("[APPROVAL] Applying pending edits...")
            edits_data = state.pending_edits.get("edits", [])
            
            if not edits_data:
                state.messages.append(AIMessage(content="No edits to apply."))
                print("Agent> No edits to apply.\n")
                state.pending_edits = {}
                continue
            
            results = []
            for edit_item in edits_data:
                if not isinstance(edit_item, dict) or "file" not in edit_item:
                    continue
                
                filepath = edit_item["file"]
                edits = edit_item.get("edits", [])
                
                if not edits:
                    results.append(f"No edits specified for {filepath}")
                    continue
                
                print(f"  → Applying {len(edits)} edits to {filepath}...")
                success, message, final_content = apply_edits_to_file(filepath, edits)
                results.append(message)
                
                if success and final_content is not None:
                    # Update session context immediately with the content we just wrote
                    state.session_context.setdefault("file_contents", {})[filepath] = final_content
                    print(f"  ✓ Updated session context for {filepath}")
            
            result_message = "Edits applied:\n" + "\n".join(f"  • {r}" for r in results)
            state.messages.append(AIMessage(content=result_message))
            state.pending_edits = {}
            print(f"Agent> {result_message}\n")
            
            # Log code changes to memory (after files have been updated in session context)
            if state.session_context.get("file_contents"):
                # Compute hash after all updates
                new_hash = compute_code_hash(state.session_context.get("file_contents", {}))
                files_modified = [e.get("file") for e in edits_data if isinstance(e, dict) and "file" in e]
                if files_modified:
                    save_memory(state.memory, {
                        "action": "code_changed",
                        "description": f"Code changed after edits (hash: {new_hash[:16]}...)",
                        "files_modified": files_modified
                    })
                    print(f"  [MEMORY] Code hash updated - query cache may be invalidated for changed files")
            
            # Auto-run tests after edits
            print("[AUTO-TEST] Running tests after edits...")
            test_result = run_tests()
            if test_result["exit_code"] == 0:
                print("Agent> ✅ All tests passed after edits!\n")
                state.messages.append(AIMessage(content="✅ All tests passed after edits!"))
            else:
                print("Agent> ⚠ Tests failed. Entering auto-fix loop...\n")
                state.messages.append(AIMessage(content=f"⚠ Tests failed after edits:\n{test_result['stdout']}\n{test_result['stderr']}\n\nEntering auto-fix loop..."))
                
                # Auto-fix loop (max 3 iterations)
                max_fix_attempts = 3
                for fix_attempt in range(max_fix_attempts):
                    print(f"[AUTO-FIX] Attempt {fix_attempt + 1}/{max_fix_attempts}")
                    
                    # Refresh file contents from disk before generating edits
                    print(f"  → Refreshing file contents from disk...")
                    for filepath in list(state.session_context.get("file_contents", {}).keys()):
                        try:
                            fresh_content = (SAMPLE_PROJECT_DIR / filepath).read_text(encoding="utf-8")
                            state.session_context["file_contents"][filepath] = fresh_content
                            cache_file(filepath, fresh_content)
                            print(f"  ✓ Refreshed {filepath}")
                        except Exception as e:
                            print(f"  ⚠ Could not refresh {filepath}: {e}")
                    
                    # Trigger edit node to fix issues
                    state.messages.append(HumanMessage(content=f"Fix the failing tests. Test errors:\n{test_result['stdout'][:1000]}\n{test_result['stderr'][:500]}"))
                    result = app.invoke(state)
                    if isinstance(result, dict):
                        if hasattr(state, 'session_context') and state.session_context:
                            if 'session_context' not in result or not result.get('session_context'):
                                result['session_context'] = state.session_context
                        state = AgentState(**result)
                    else:
                        state = result
                    
                    # Check if edits were generated
                    if state.pending_edits:
                        print(f"[AUTO-FIX] Applying fixes (attempt {fix_attempt + 1})...")
                        # Apply the fixes
                        edits_data = state.pending_edits.get("edits", [])
                        applied_any = False
                        for edit_item in edits_data:
                            if isinstance(edit_item, dict) and "file" in edit_item:
                                filepath = edit_item["file"]
                                edits = edit_item.get("edits", [])
                                if edits:
                                    print(f"  → Applying {len(edits)} edits to {filepath}...")
                                    success, msg, final_content = apply_edits_to_file(filepath, edits)
                                    print(f"  → {msg}")
                                    if success:
                                        applied_any = True
                                        # Update session context immediately with the content we just wrote
                                        if final_content is not None:
                                            state.session_context.setdefault("file_contents", {})[filepath] = final_content
                                            print(f"  ✓ Updated session context for {filepath}")
                        
                        state.pending_edits = {}
                        
                        if not applied_any:
                            print(f"  → No edits were successfully applied, breaking loop")
                            break
                        
                        # Re-run tests
                        test_result = run_tests()
                        if test_result["exit_code"] == 0:
                            print(f"Agent> ✅ Tests passed after auto-fix (attempt {fix_attempt + 1})!\n")
                            state.messages.append(AIMessage(content=f"✅ Tests passed after auto-fix (attempt {fix_attempt + 1})!"))
                            break
                        else:
                            print(f"  → Tests still failing, continuing fix loop...")
                            if fix_attempt < max_fix_attempts - 1:
                                print(f"  → Failure details:\n{test_result['stdout'][:500]}")
                    else:
                        print(f"  → No fixes generated, breaking loop")
                        break
                else:
                    print(f"Agent> ⚠ Auto-fix loop completed. Tests may still be failing.\n")
                    state.messages.append(AIMessage(content="⚠ Auto-fix loop completed. Please review manually."))
            
            continue
        
        state.messages.append(HumanMessage(content=user_input))
        result = app.invoke(state)
        # Convert dict back to AgentState, preserving session_context and memory
        if isinstance(result, dict):
            # Preserve session context across invocations
            if hasattr(state, 'session_context') and state.session_context:
                if 'session_context' not in result or not result.get('session_context'):
                    result['session_context'] = state.session_context
                else:
                    # Merge session contexts
                    existing = result.get('session_context', {})
                    existing['read_files'] = list(set(existing.get('read_files', []) + state.session_context.get('read_files', [])))
                    existing['file_contents'] = {**state.session_context.get('file_contents', {}), **existing.get('file_contents', {})}
                    existing['conversation_history'] = state.session_context.get('conversation_history', []) + existing.get('conversation_history', [])
                    # Keep only last 10
                    if len(existing['conversation_history']) > 10:
                        existing['conversation_history'] = existing['conversation_history'][-10:]
                    result['session_context'] = existing
            # Preserve memory across invocations (cache is saved to file immediately when updated)
            # Reload memory from file to ensure we have the latest persisted cache
            if hasattr(state, 'memory') and state.memory:
                # Merge in-memory updates with file-based cache
                file_memory = load_memory()
                # Preserve any in-memory updates that haven't been saved yet
                if 'query_cache' in state.memory:
                    file_memory['query_cache'].update(state.memory.get('query_cache', {}))
                result['memory'] = file_memory
            else:
                result['memory'] = load_memory()
            state = AgentState(**result)
        else:
            state = result
        
        responses = [m for m in state.messages if isinstance(m, AIMessage)]
        if responses:
            print("Agent>", responses[-1].content, "\n")
        state.done = False


if __name__ == "__main__":
    main()