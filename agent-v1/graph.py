import asyncio
import json
import re
import time
from pathlib import Path
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from mcps.edit_mcp import plan_edits
from mcps.execution_mcp import run_command
from mcps.filesystem_mcp import cache_file, list_python_files
from mcps.intent_mcp import classify_intent
from config.llm_config import get_llm
from config.logger_config import get_logger
from mcps.logging_mcp import log_node_execution
from mcps.memory_mcp import update_preferences_from_text
from mcps.read_mcp import retrieve_context
from state import AgentState, last_user_text

logger = get_logger()

MAX_CONTEXT_LENGTH = 50000
MAX_CONVERSATION_HISTORY = 10


def truncate_context(content: str, max_length: int = MAX_CONTEXT_LENGTH) -> str:
    """Truncate content if it exceeds max_length, keeping the beginning"""
    if len(content) <= max_length:
        return content
    logger.warning(f"Context truncated from {len(content)} to {max_length} characters")
    return content[:max_length] + "\n... [truncated]"


def manage_conversation_history(state: AgentState, max_items: int = MAX_CONVERSATION_HISTORY) -> None:
    """Manage conversation history length to prevent context overflow"""
    history = state.session_context.get("conversation_history", [])
    if len(history) > max_items:
        state.session_context["conversation_history"] = history[-max_items:]
        logger.debug(f"Truncated conversation history from {len(history)} to {max_items} items")


def with_error_handling(node_name: str):
    """Decorator to wrap node functions with error handling and recovery"""
    def decorator(func):
        async def wrapper(state: AgentState) -> AgentState:
            state.working_memory["current_node"] = node_name
            state.working_memory["current_step"] = "starting"
            
            try:
                result = await func(state)
                state.working_memory["current_step"] = "completed"
                state.working_memory["retry_count"] = 0
                state.working_memory["last_error"] = None
                return result
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error in {node_name}: {error_msg}", exc_info=True)
                state.working_memory["last_error"] = error_msg
                state.working_memory["retry_count"] = state.working_memory.get("retry_count", 0) + 1
                
                state.working_memory["feedback_history"].append({
                    "node": node_name,
                    "error": error_msg,
                    "retry_count": state.working_memory["retry_count"],
                    "timestamp": time.time()
                })
                
                max_retries = 3
                if state.working_memory["retry_count"] > max_retries:
                    error_response = f"Error in {node_name} after {max_retries} attempts: {error_msg}\nPlease try a different approach or check the logs."
                    state.messages.append(AIMessage(content=error_response))
                    state.done = True
                    state.working_memory["current_step"] = "failed"
                    return state
                
                recovery_msg = f"⚠ Error in {node_name}: {error_msg}. Retrying... (attempt {state.working_memory['retry_count']}/{max_retries})"
                state.messages.append(AIMessage(content=recovery_msg))
                state.working_memory["current_step"] = "retrying"
                
                raise
        return wrapper
    return decorator


@with_error_handling("route")
async def route_node(state: AgentState) -> AgentState:
    logger.debug("route_node()")
    start_time = time.time()
    state.working_memory["current_step"] = "classifying_intent"
    text = last_user_text(state)
    input_summary = {
        "user_text": text[:100] if text else "",
        "intent": state.intent,
        "messages_count": len(state.messages)
    }
    if update_preferences_from_text(state.memory, text):
        state.intent = "profile"
        print(f"→ Intent: profile (from preferences)")
        duration = time.time() - start_time
        output_summary = {"intent": state.intent, "done": False}
        log_node_execution(state.memory, "route", input_summary, output_summary, duration)
        return state
    
    state.intent = await classify_intent(state, text)
    print(f"→ Intent: {state.intent}")
    
    duration = time.time() - start_time
    output_summary = {"intent": state.intent, "done": state.done}
    log_node_execution(state.memory, "route", input_summary, output_summary, duration)
    return state


@with_error_handling("profile")
async def profile_node(state: AgentState) -> AgentState:
    logger.debug("profile_node()")
    start_time = time.time()
    state.working_memory["current_step"] = "loading_preferences"
    prefs = state.memory.get("preferences", {})
    logger.info(f"Preferences: {prefs}")
    
    pref_messages = []
    if prefs.get("write_comments"):
        pref_messages.append("✓ Always write comments while editing")
    if prefs.get("add_docstrings"):
        pref_messages.append("✓ Always add docstrings to new functions/classes")
    if not pref_messages:
        pref_messages.append("No active preferences")
    
    message = "Preferences saved:\n" + "\n".join(f"  {m}" for m in pref_messages)
    state.messages.append(AIMessage(content=message))
    print(f"Agent> {message}\n")
    state.done = True
    
    duration = time.time() - start_time
    log_node_execution(state.memory, "profile", {"preferences": prefs}, {"done": True}, duration)
    return state


@with_error_handling("plan_read")
async def plan_read_node(state: AgentState) -> AgentState:
    logger.debug("plan_read_node()")
    start_time = time.time()
    state.working_memory["current_step"] = "listing_files"
    files = list_python_files()
    input_summary = {
        "already_read_count": len(state.session_context.get("read_files", [])),
        "available_files_count": len(files)
    }
    
    already_read = state.session_context.get("read_files", [])
    if already_read:
        logger.info(f"Previously read in session: {len(already_read)} files")
    
    sys = SystemMessage(
        content=(
            "Select which files to read. Return JSON list.\n"
            f"Files already read in this session: {already_read}\n"
            "You can select new files or reuse already read ones."
        )
    )
    logger.debug("Calling LLM to select files")
    logger.debug(f"Available files: {len(files)} files, Already read: {len(already_read)} files")
    
    context_msg = f"Available: {json.dumps(files)}\nAlready read: {json.dumps(already_read)}"
    llm = get_llm()
    msg = await llm.ainvoke([sys, HumanMessage(content=context_msg)])
    logger.debug(f"LLM response: {msg.content[:200]}...")
    
    try:
        content = msg.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
        
        logger.debug(f"Extracted JSON: {content[:200]}...")
        selected = json.loads(content)
        if not isinstance(selected, list):
            selected = [selected]
        
        valid_files = [f for f in selected if f in files]
        if not valid_files:
            logger.warning("No valid files found in selection, using all files")
            state.target_files = files
        else:
            state.target_files = valid_files
            print(f"→ Selected {len(state.target_files)} files")
    except Exception as e:
        logger.warning(f"Failed to parse JSON: {e}")
        print(f"→ Using all {len(files)} files")
        state.target_files = files
    
    duration = time.time() - start_time
    output_summary = {
        "target_files_count": len(state.target_files),
        "target_files": state.target_files[:5]
    }
    log_node_execution(state.memory, "plan_read", input_summary, output_summary, duration)
    return state


@with_error_handling("read")
async def read_node(state: AgentState) -> AgentState:
    logger.debug("read_node()")
    node_start_time = time.time()
    state.working_memory["current_step"] = "retrieving_context"
    print(f"→ Reading {len(state.target_files)} files...")
    
    user_question = last_user_text(state)
    manage_conversation_history(state)
    input_summary = {
        "target_files_count": len(state.target_files),
        "target_files": state.target_files[:3],
        "user_question": user_question[:100] if user_question else ""
    }
    
    response, file_contents_map = await retrieve_context(state, user_question)
    
    state.messages.append(AIMessage(content=response))
    state.done = True
    
    state.session_context["conversation_history"].append({
        "q": user_question[:500],  # Truncate questions
        "a": response[:2000]  # Truncate answers
    })
    manage_conversation_history(state)
    
    duration = time.time() - node_start_time
    output_summary = {
        "files_read_count": len(state.target_files),
        "total_content_size": sum(len(state.session_context.get("file_contents", {}).get(f, "")) for f in state.target_files),
        "used_cache": response != user_question,
        "response_length": len(response)
    }
    log_node_execution(state.memory, "read", input_summary, output_summary, duration)
    return state


@with_error_handling("edit")
async def edit_node(state: AgentState) -> AgentState:
    logger.debug("edit_node()")
    node_start_time = time.time()
    state.working_memory["current_step"] = "planning_edits"
    user_request = last_user_text(state)
    
    recent_failures = [f for f in state.working_memory.get("feedback_history", []) 
                      if f.get("node") == "edit" and len(state.working_memory.get("feedback_history", [])) - state.working_memory.get("feedback_history", []).index(f) <= 3]
    if recent_failures:
        logger.info(f"Previous edit failures detected: {len(recent_failures)}")
        user_request += f"\n\n[Note: Previous edit attempts failed. Please review carefully and ensure edits are valid.]"
    input_summary = {
        "user_request": user_request[:100] if user_request else "",
        "session_files_count": len(state.session_context.get("file_contents", {}))
    }
    
    session_files = state.session_context.get("file_contents", {})
    if not session_files:
        logger.info("No files in session, reading all Python files")
        all_files = list_python_files()
        state.target_files = all_files
        state = await read_node(state)
        session_files = state.session_context.get("file_contents", {})
    
    logger.info(f"Using {len(session_files)} files from session context")   
    
    edit_plan = await plan_edits(state, user_request, read_node_func=read_node)
    
    state.pending_edits = edit_plan
    
    edit_summary = f"Edit plan generated for {len(edit_plan['files'])} files:\n\n"
    for edit_item in edit_plan["edits"]:
        if isinstance(edit_item, dict) and "file" in edit_item:
            edit_summary += f"File: {edit_item['file']}\n"
            if "edits" in edit_item:
                num_edits = len(edit_item['edits'])
                edit_summary += f"  {num_edits} edit(s) planned\n"
                for i, edit in enumerate(edit_item['edits'][:3]):
                    line = edit.get('line', '?')
                    edit_summary += f"    - Line {line}\n"
    
    edit_summary += f"\nTotal: {edit_plan['total_edits']} edit(s) across {len(edit_plan['files'])} file(s)"
    edit_summary += "\n\nType 'approve' to apply changes, or ask for modifications."
    
    state.messages.append(AIMessage(content=edit_summary))
    state.done = True
    
    duration = time.time() - node_start_time
    output_summary = {
        "files_to_edit_count": len(edit_plan['files']),
        "total_edits_planned": edit_plan['total_edits'],
        "has_pending_edits": bool(state.pending_edits)
    }
    log_node_execution(state.memory, "edit", input_summary, output_summary, duration)
    return state


@with_error_handling("run_command")
async def run_command_node(state: AgentState) -> AgentState:
    logger.debug("run_command_node()")
    node_start_time = time.time()
    state.working_memory["current_step"] = "parsing_command"
    user_text = last_user_text(state)
    
    if state.selected_command:
        command = state.selected_command
    else:
        user_lower = user_text.lower() if user_text else ""
        command = ["pytest"]  # default
        
        if "run test" in user_lower or "test" in user_lower:
            command = ["pytest"]
        elif "run main" in user_lower or "run main.py" in user_lower or "run main file" in user_lower:
            command = ["python", "main.py"]
        elif "run python" in user_lower:
            parts = user_text.split()
            python_idx = -1
            for i, part in enumerate(parts):
                if part.lower() in ["python", "python3"]:
                    python_idx = i
                    break
            if python_idx >= 0 and python_idx + 1 < len(parts):
                filename = parts[python_idx + 1]
                command = ["python", filename]
            else:
                py_files = re.findall(r'\b\w+\.py\b', user_text)
                if py_files:
                    command = ["python", py_files[0]]
        elif ".py" in user_text:
            py_files = re.findall(r'\b\w+\.py\b', user_text)
            if py_files:
                command = ["python", py_files[0]]
        else:
            sys = SystemMessage(
                content=(
                    "Parse the user's command request and return a JSON array with the command to run.\n"
                    "Examples:\n"
                    "- 'run pytest' -> [\"pytest\"]\n"
                    "- 'run main.py' -> [\"python\", \"main.py\"]\n"
                    "- 'run python app.py' -> [\"python\", \"app.py\"]\n"
                    "- 'run curl http://example.com' -> [\"curl\", \"http://example.com\"]\n"
                    "Return only the JSON array, no other text."
                )
            )
            llm = get_llm()
            msg = await llm.ainvoke([sys, HumanMessage(content=user_text)])
            try:
                content = msg.content.strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    parts = content.split("```")
                    if len(parts) >= 3:
                        content = parts[1].strip()
                        if content.startswith("json"):
                            content = content[4:].strip()
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    command = parsed
            except Exception as e:
                logger.warning(f"Failed to parse command from LLM: {e}, using default pytest")
    
    input_summary = {
        "command": command,
        "selected_command": state.selected_command is not None,
        "user_text": user_text[:100] if user_text else ""
    }
    result = run_command(command)
    
    exit_code = result.get("exit_code", 0)
    stdout = result.get("stdout", "")
    
    feedback_entry = {
        "type": "command_execution",
        "command": command,
        "exit_code": exit_code,
        "success": exit_code == 0,
        "timestamp": time.time()
    }
    state.working_memory["feedback_history"].append(feedback_entry)
    
    if len(state.working_memory["feedback_history"]) > 20:
        state.working_memory["feedback_history"] = state.working_memory["feedback_history"][-20:]
    
    if exit_code != 0:
        error_context = f"\n[Previous command failed with exit code {exit_code}. Review errors above.]"
        stdout = stdout + error_context
        logger.info(f"Command failed, adding error context for future corrections")
    
    state.messages.append(AIMessage(content=stdout))
    state.done = True
    duration = time.time() - node_start_time
    output_summary = {
        "command": command,
        "result": result
    }
    log_node_execution(state.memory, "run_command", input_summary, output_summary, duration)
    return state


@with_error_handling("undo")
async def undo_node(state: AgentState) -> AgentState:
    logger.debug("undo_node()")
    node_start_time = time.time()
    state.working_memory["current_step"] = "checking_history"
    
    input_summary = {
        "edit_history_length": len(state.edit_history),
        "user_text": last_user_text(state)[:100] if last_user_text(state) else ""
    }
    
    if not state.edit_history:
        message = "No edit history found. Nothing to undo."
        state.messages.append(AIMessage(content=message))
        state.done = True
        print(f"Agent> {message}\n")
        
        duration = time.time() - node_start_time
        output_summary = {"undone": False, "reason": "no_history"}
        log_node_execution(state.memory, "undo", input_summary, output_summary, duration)
        return state
    
    last_edit = state.edit_history[-1]
    backups = last_edit.get("backups", {})
    files_to_restore = list(backups.keys())
    
    if not files_to_restore:
        message = "No file backups found in last edit. Cannot undo."
        state.messages.append(AIMessage(content=message))
        state.done = True
        print(f"Agent> {message}\n")
        
        duration = time.time() - node_start_time
        output_summary = {"undone": False, "reason": "no_backups"}
        log_node_execution(state.memory, "undo", input_summary, output_summary, duration)
        return state
    
    BASE_DIR = Path(__file__).resolve().parent
    SAMPLE_PROJECT_DIR = BASE_DIR / "../sampleProject"
    
    restored_files = []
    failed_files = []
    
    for filepath in files_to_restore:
        try:
            backup_content = backups[filepath]
            file_path = SAMPLE_PROJECT_DIR / filepath
            file_path.write_text(backup_content, encoding="utf-8")
            
            state.session_context.setdefault("file_contents", {})[filepath] = backup_content
            cache_file(filepath, backup_content)
            
            restored_files.append(filepath)
            logger.info(f"Restored {filepath} from backup")
        except Exception as e:
            logger.error(f"Failed to restore {filepath}: {e}")
            failed_files.append(f"{filepath}: {str(e)}")
    
    undone_edits = last_edit.get("edits_applied", [])
    
    state.edit_history.pop()
    
    if undone_edits:
        changes_json = json.dumps(undone_edits, indent=2)
        print(f"Undone changes JSON:\n{changes_json}\n")
    
    if restored_files:
        message = f"✅ Undone last edit. Restored {len(restored_files)} file(s):\n"
        message += "\n".join(f"  • {f}" for f in restored_files)
        if failed_files:
            message += f"\n\n⚠ Failed to restore:\n" + "\n".join(f"  • {f}" for f in failed_files)
    else:
        message = f"❌ Failed to restore any files:\n" + "\n".join(f"  • {f}" for f in failed_files)
    
    state.messages.append(AIMessage(content=message))
    state.done = True
    print(f"Agent> {message}\n")
    
    duration = time.time() - node_start_time
    output_summary = {
        "undone": len(restored_files) > 0,
        "files_restored": restored_files,
        "files_failed": failed_files
    }
    log_node_execution(state.memory, "undo", input_summary, output_summary, duration)
    return state


def build_graph():
    graph = StateGraph(AgentState)
    
    graph.add_node("route", route_node)
    graph.add_node("profile", profile_node)
    graph.add_node("plan_read", plan_read_node)
    graph.add_node("read", read_node)
    graph.add_node("edit", edit_node)
    graph.add_node("run_command", run_command_node)
    graph.add_node("undo", undo_node)
    
    graph.add_edge(START, "route")
    
    graph.add_conditional_edges(
        "route",
        lambda s: s.intent,
        {
            "profile": "profile",
            "read": "plan_read",
            "edit": "edit",
            "run_command": "run_command",
            "undo": "undo",
        },
    )
    
    graph.add_edge("plan_read", "read")
    graph.add_edge("profile", END)
    graph.add_edge("read", END)
    graph.add_edge("edit", END)
    graph.add_edge("run_command", END)
    graph.add_edge("undo", END)
    
    return graph.compile()

