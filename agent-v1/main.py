import asyncio
import os
from pathlib import Path

import ray
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from graph import build_graph
from mcps.execution_mcp import run_pytest
from mcps.filesystem_mcp import apply_line_edits, cache_file, clear_file_cache
from mcps.llm_config import initialize_llm
from mcps.logger_config import get_logger
from mcps.memory_mcp import compute_code_hash, load_memory, save_memory
from state import AgentState

logger = get_logger()

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_PROJECT_DIR = BASE_DIR / "../sampleProject"

# Load .env file from agent-v1 directory or parent directory
env_file = BASE_DIR / ".env"
if not env_file.exists():
    env_file = BASE_DIR.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    logger.info(f"Loaded environment variables from {env_file}")
else:
    load_dotenv()  # Try default .env in current directory

# Suppress Ray metrics exporter errors
os.environ.setdefault("RAY_DISABLE_IMPORT_WARNING", "1")
os.environ.setdefault("RAY_IGNORE_UNHANDLED_ERRORS", "1")
os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")
os.environ.setdefault("RAY_USAGE_STATS_ENABLED", "0")
os.environ.setdefault("RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER", "0")

# Suppress Ray logging to stderr
import logging
import sys
from io import StringIO

ray_logger = logging.getLogger("ray")
ray_logger.setLevel(logging.CRITICAL)

# Filter stderr to remove Ray metrics exporter errors
class RayErrorFilter:
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
    
    def write(self, text):
        # Filter out Ray metrics exporter errors and related messages
        text_lower = text.lower()
        
        # Check for Ray/metrics/exporter related errors
        ray_error_keywords = [
            "failed to establish connection to the metrics exporter",
            "core_worker_process.cc",
            "metrics exporter agent",
            "metrics will not be exported",
            "exporter agent status",
            "rpc_error: running out of retries",
            "rpc_code: 14",
            "unimplemented",
            "grpc exporter",
            "batch span processor",
            "otlp receiver",
            "max_recv_msg_size",
            "e ",  # Ray error prefix like "E 61987 832054"
            "core_worker"
        ]
        
        # Suppress if it contains any error keywords AND is related to Ray/metrics
        if any(keyword in text_lower for keyword in ray_error_keywords):
            # Additional check: must be error/warning level or contain Ray/metrics context
            if any(indicator in text_lower for indicator in ["e ", "error", "warning", "ray", "metrics", "exporter", "rpc"]):
                return  # Suppress this message
        
        self.original_stderr.write(text)
    
    def flush(self):
        self.original_stderr.flush()
    
    def fileno(self):
        """Required by Ray's faulthandler"""
        return self.original_stderr.fileno()
    
    def isatty(self):
        """File-like interface method"""
        return self.original_stderr.isatty()
    
    def readable(self):
        """File-like interface method"""
        return self.original_stderr.readable()
    
    def writable(self):
        """File-like interface method"""
        return self.original_stderr.writable()
    
    def seekable(self):
        """File-like interface method"""
        return self.original_stderr.seekable()

# Install stderr filter before Ray initialization
_original_stderr = sys.stderr
sys.stderr = RayErrorFilter(_original_stderr)

if not ray.is_initialized():
    ray.init(
        ignore_reinit_error=True,
        include_dashboard=False,
        log_to_driver=False,
        _enable_object_reconstruction=False,
        _metrics_export_port=None,
    )


def check_environment() -> None:
    """Check required environment variables"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY environment variable is not set")
        print("Please set it using: export DEEPSEEK_API_KEY='your-api-key'")
        print("Or add it to your .env file")
        raise SystemExit(1)


def print_startup_info(state: AgentState) -> None:
    print("AI Coding Agent (LangGraph + DeepSeek + Ray)")
    print("Type 'exit' or 'quit' to stop.\n")
    print("Session context will be maintained across requests.\n")
    
    cache_size = len(state.memory.get("query_cache", {}))
    node_log_size = len(state.memory.get("node_log", []))
    
    if cache_size > 0:
        print(f"[MEMORY] Loaded {cache_size} cached query responses from file")
        print(f"[MEMORY] Cache will be reused when code hasn't changed")
    else:
        print(f"[MEMORY] No cached responses found. Cache will be built as queries are made.")
    
    if node_log_size > 0:
        print(f"[MEMORY] Loaded {node_log_size} node execution logs from file")
        recent_nodes = state.memory.get("node_log", [])[-5:]
        print(f"[MEMORY] Recent node executions:")
        for log_entry in recent_nodes:
            node_name = log_entry.get("node_name", "unknown")
            timestamp = log_entry.get("timestamp", "")[:19]
            duration = log_entry.get("duration_seconds", 0)
            print(f"  - {node_name} ({timestamp}, {duration:.3f}s)")
    print()


def apply_pending_edits(state: AgentState) -> tuple[bool, str]:
    edits_data = state.pending_edits.get("edits", [])
    if not edits_data:
        state.messages.append(AIMessage(content="No edits to apply."))
        print("Agent> No edits to apply.\n")
        state.pending_edits = {}
        return False, ""
    
    results = []
    for edit_item in edits_data:
        if not isinstance(edit_item, dict) or "file" not in edit_item:
            continue
        
        filepath = edit_item["file"]
        edits = edit_item.get("edits", [])
        if not edits:
            results.append(f"No edits specified for {filepath}")
            continue
        
        print(f"→ Applying {len(edits)} edits to {filepath}...")
        success, message, final_content = apply_line_edits(filepath, edits)
        results.append(message)
        
        if success and final_content is not None:
            # Update session context with fresh content from disk
            state.session_context.setdefault("file_contents", {})[filepath] = final_content
            # Also update the file cache to ensure consistency
            cache_file(filepath, final_content)
            logger.debug(f"Updated session context and cache for {filepath}")
    
    result_message = "Edits applied:\n" + "\n".join(f"  • {r}" for r in results)
    state.messages.append(AIMessage(content=result_message))
    state.pending_edits = {}
    print(f"Agent> {result_message}\n")
    
    if state.session_context.get("file_contents"):
        new_hash = compute_code_hash(state.session_context.get("file_contents", {}))
        files_modified = [e.get("file") for e in edits_data if isinstance(e, dict) and "file" in e]
        if files_modified:
            save_memory(state.memory, {
                "action": "code_changed",
                "description": f"Code changed after edits (hash: {new_hash[:16]}...)",
                "files_modified": files_modified
            })
            logger.info("Code hash updated - query cache may be invalidated for changed files")
    
    return True, result_message


def refresh_file_contents(state: AgentState) -> None:
    """Refresh all file contents in session context from disk to ensure consistency"""
    logger.info("Refreshing file contents from disk")
    refreshed_count = 0
    for filepath in list(state.session_context.get("file_contents", {}).keys()):
        try:
            fresh_content = (SAMPLE_PROJECT_DIR / filepath).read_text(encoding="utf-8")
            state.session_context["file_contents"][filepath] = fresh_content
            cache_file(filepath, fresh_content)
            refreshed_count += 1
            logger.debug(f"Refreshed {filepath}")
        except Exception as e:
            logger.warning(f"Could not refresh {filepath}: {e}")
    logger.info(f"Refreshed {refreshed_count} files from disk")


async def auto_fix_loop(app, state: AgentState, test_result: dict) -> AgentState:
    max_fix_attempts = 3
    print("Agent> ⚠ Tests failed. Entering auto-fix loop...\n")
    state.messages.append(AIMessage(content=f"⚠ Tests failed after edits:\n{test_result['stdout']}\n{test_result['stderr']}\n\nEntering auto-fix loop..."))
    
    for fix_attempt in range(max_fix_attempts):
        print(f"[AUTO-FIX] Attempt {fix_attempt + 1}/{max_fix_attempts}")
        refresh_file_contents(state)
        
        state.messages.append(HumanMessage(content=f"Fix the failing tests. Test errors:\n{test_result['stdout'][:1000]}\n{test_result['stderr'][:500]}"))
        result = await app.ainvoke(state)
        state = _preserve_state(state, result)
        
        if not state.pending_edits:
            logger.info("No fixes generated, breaking loop")
            break
        
        print(f"→ Applying fixes (attempt {fix_attempt + 1})...")
        edits_data = state.pending_edits.get("edits", [])
        applied_any = False
        
        for edit_item in edits_data:
            if isinstance(edit_item, dict) and "file" in edit_item:
                filepath = edit_item["file"]
                edits = edit_item.get("edits", [])
                if edits:
                    logger.info(f"Applying {len(edits)} edits to {filepath}")
                    success, msg, final_content = apply_line_edits(filepath, edits)
                    logger.debug(f"{msg}")
                    if success and final_content is not None:
                        applied_any = True
                        state.session_context.setdefault("file_contents", {})[filepath] = final_content
                        logger.debug(f"Updated session context for {filepath}")
        
        state.pending_edits = {}
        if not applied_any:
            logger.info("No edits were successfully applied, breaking loop")
            break
        
        test_result = run_pytest()
        if test_result["exit_code"] == 0:
            print(f"Agent> ✅ Tests passed after auto-fix (attempt {fix_attempt + 1})!\n")
            state.messages.append(AIMessage(content=f"✅ Tests passed after auto-fix (attempt {fix_attempt + 1})!"))
            break
        else:
            logger.info("Tests still failing, continuing fix loop")
            if fix_attempt < max_fix_attempts - 1:
                logger.debug(f"Failure details: {test_result['stdout'][:500]}")
    else:
        print(f"Agent> ⚠ Auto-fix loop completed. Tests may still be failing.\n")
        state.messages.append(AIMessage(content="⚠ Auto-fix loop completed. Please review manually."))
    
    return state


def _preserve_state(state: AgentState, result) -> AgentState:
    if isinstance(result, dict):
        if hasattr(state, 'session_context') and state.session_context:
            if 'session_context' not in result or not result.get('session_context'):
                result['session_context'] = state.session_context
            else:
                existing = result.get('session_context', {})
                existing['read_files'] = list(set(existing.get('read_files', []) + state.session_context.get('read_files', [])))
                existing['file_contents'] = {**state.session_context.get('file_contents', {}), **existing.get('file_contents', {})}
                existing['conversation_history'] = state.session_context.get('conversation_history', []) + existing.get('conversation_history', [])
                if len(existing['conversation_history']) > 10:
                    existing['conversation_history'] = existing['conversation_history'][-10:]
                result['session_context'] = existing
        
        if hasattr(state, 'memory') and state.memory:
            file_memory = load_memory()
            if 'query_cache' in state.memory:
                file_memory['query_cache'].update(state.memory.get('query_cache', {}))
            result['memory'] = file_memory
        else:
            result['memory'] = load_memory()
        return AgentState(**result)
    return result


async def main():
    check_environment()
    initialize_llm()
    
    # Clear file cache on startup to ensure fresh reads
    clear_file_cache()
    logger.info("File cache cleared - starting fresh session")
    
    app = build_graph()
    state = AgentState()  # Fresh state with empty session context
    print_startup_info(state)

    while True:
        user_input = input("You> ")
        if user_input.lower() in {"exit", "quit"}:
            break
        
        if user_input.lower() == "approve" and state.pending_edits:
            print("→ Applying pending edits...")
            applied, result_msg = apply_pending_edits(state)
            if not applied:
                continue
            
            print("→ Running tests after edits...")
            test_result = run_pytest()
            if test_result["exit_code"] == 0:
                print("Agent> ✅ All tests passed after edits!\n")
                state.messages.append(AIMessage(content="✅ All tests passed after edits!"))
            else:
                state = await auto_fix_loop(app, state, test_result)
            continue
        
        state.messages.append(HumanMessage(content=user_input))
        result = await app.ainvoke(state)
        state = _preserve_state(state, result)
        
        responses = [m for m in state.messages if isinstance(m, AIMessage)]
        if responses:
            print("Agent>", responses[-1].content, "\n")
        state.done = False


if __name__ == "__main__":
    asyncio.run(main())
