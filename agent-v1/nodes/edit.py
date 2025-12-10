"""
Edit Node - Generate and apply code edits
"""
import json
import os
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from tools.mcp_adapter import mcp_adapter
from tools.filesystem import backup_file


async def edit_node(state: AgentState) -> AgentState:
    """Plan and prepare edits"""
    
    # Get user request
    user_msg = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break
    
    if not user_msg:
        state.messages.append(AIMessage(content="No edit request found."))
        state.done = True
        return state
    
    # Select files if not already selected
    if not state.target_files:
        files = await mcp_adapter.list_files()
        llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=0
        )
        prompt = f"Available files:\n{chr(10).join(files)}\n\nEdit request: {user_msg}\n\nWhich files need editing? Return comma-separated list."
        response = llm.invoke([SystemMessage(content=prompt)])
        selected = [f.strip() for f in response.content.split(",") if f.strip() in files]
        state.target_files = selected[:3]  # Limit to 3 files
    
    # Read files
    for filepath in state.target_files:
        content = await mcp_adapter.read_file(filepath)
        state.memory.add_file(filepath, content)
    
    # Generate edit plan
    context = state.memory.get_context(state.target_files)
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com",
        temperature=0
    )
    
    prompt = SystemMessage(content=(
        f"Generate edits for: {user_msg}\n\n"
        f"Code:\n{context}\n\n"
        "Return JSON: {\"file\": \"path\", \"edits\": [{\"start\": line, \"end\": line, \"content\": \"new code\"}]}"
    ))
    
    response = llm.invoke([prompt])
    
    # Parse edit plan
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        edit_plan = json.loads(content.strip())
        state.pending_edits = edit_plan
        
        # Show plan to user
        summary = f"Edit plan for {edit_plan['file']}:\n"
        for edit in edit_plan.get("edits", []):
            summary += f"- Lines {edit['start']}-{edit['end']}: {edit.get('description', 'modify')}\n"
        
        state.messages.append(AIMessage(content=f"{summary}\n\nType 'approve' to apply these edits."))
        
    except Exception as e:
        state.messages.append(AIMessage(content=f"Failed to generate edit plan: {e}"))
    
    state.done = True
    return state


async def apply_edits(state: AgentState) -> AgentState:
    """Apply pending edits"""
    
    if not state.pending_edits:
        return state
    
    filepath = state.pending_edits["file"]
    edits = state.pending_edits.get("edits", [])
    
    # Backup
    backup = backup_file(filepath)
    state.edit_history.append({
        "file": filepath,
        "backup": backup,
        "timestamp": str(datetime.now())
    })
    
    # Read current content
    content = await mcp_adapter.read_file(filepath)
    lines = content.split("\n")
    
    # Apply edits (reverse order to maintain line numbers)
    for edit in sorted(edits, key=lambda x: x["start"], reverse=True):
        start = edit["start"] - 1  # Convert to 0-indexed
        end = edit["end"]
        new_content = edit["content"]
        lines[start:end] = new_content.split("\n")
    
    # Write back
    new_content = "\n".join(lines)
    await mcp_adapter.write_file(filepath, new_content)
    state.memory.add_file(filepath, new_content)
    
    state.messages.append(AIMessage(content=f"Applied edits to {filepath}"))
    state.pending_edits = {}
    
    # Run tests
    result = await mcp_adapter.run_command(["pytest", "-xvs"])
    if result["success"]:
        state.messages.append(AIMessage(content="Tests passed!"))
    else:
        state.messages.append(AIMessage(content=f"Tests failed:\n{result['stderr'][:500]}"))
    
    state.done = True
    return state

