import asyncio
import json
import time
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from mcps.edit_mcp import plan_edits
from mcps.execution_mcp import run_pytest
from mcps.filesystem_mcp import list_python_files
from mcps.intent_mcp import classify_intent
from mcps.llm_config import get_llm
from mcps.logger_config import get_logger
from mcps.logging_mcp import log_node_execution
from mcps.memory_mcp import update_preferences_from_text
from mcps.read_mcp import retrieve_context
from state import AgentState, last_user_text

logger = get_logger()


async def route_node(state: AgentState) -> AgentState:
    logger.debug("route_node()")
    start_time = time.time()
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


async def profile_node(state: AgentState) -> AgentState:
    logger.debug("profile_node()")
    start_time = time.time()
    prefs = state.memory.get("preferences", {})
    logger.info(f"Preferences: {prefs}")
    
    # Create a user-friendly message about saved preferences
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


async def plan_read_node(state: AgentState) -> AgentState:
    logger.debug("plan_read_node()")
    start_time = time.time()
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


async def read_node(state: AgentState) -> AgentState:
    logger.debug("read_node()")
    node_start_time = time.time()
    print(f"→ Reading {len(state.target_files)} files...")
    
    user_question = last_user_text(state)
    input_summary = {
        "target_files_count": len(state.target_files),
        "target_files": state.target_files[:3],
        "user_question": user_question[:100] if user_question else ""
    }
    
    response, file_contents_map = await retrieve_context(state, user_question)
    
    state.messages.append(AIMessage(content=response))
    state.done = True
    
    state.session_context["conversation_history"].append({
        "q": user_question,
        "a": response
    })
    if len(state.session_context["conversation_history"]) > 10:
        state.session_context["conversation_history"] = state.session_context["conversation_history"][-10:]
    
    duration = time.time() - node_start_time
    output_summary = {
        "files_read_count": len(state.target_files),
        "total_content_size": sum(len(state.session_context.get("file_contents", {}).get(f, "")) for f in state.target_files),
        "used_cache": response != user_question,
        "response_length": len(response)
    }
    log_node_execution(state.memory, "read", input_summary, output_summary, duration)
    return state


async def edit_node(state: AgentState) -> AgentState:
    logger.debug("edit_node()")
    node_start_time = time.time()
    user_request = last_user_text(state)
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


async def run_tests_node(state: AgentState) -> AgentState:
    logger.debug("run_tests_node()")
    node_start_time = time.time()
    result = run_pytest()
    input_summary = {}
    
    if result["exit_code"] == 0:
        print(f"→ All tests passed")
        state.messages.append(AIMessage(content="✅ All tests passed."))
    else:
        print(f"→ Tests failed")
        state.messages.append(
            AIMessage(content=f"❌ Tests failed:\n\n{result['stdout']}\n{result['stderr']}")
        )
    state.done = True
    
    duration = time.time() - node_start_time
    output_summary = {
        "exit_code": result["exit_code"],
        "tests_passed": result["exit_code"] == 0,
        "stdout_length": len(result.get("stdout", "")),
        "stderr_length": len(result.get("stderr", ""))
    }
    log_node_execution(state.memory, "run_tests", input_summary, output_summary, duration)
    return state


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

