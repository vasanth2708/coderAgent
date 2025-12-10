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
        
        # Check recent messages for test errors with file info
        recent_context = ""
        for msg in state.messages[-5:]:  # Last 5 messages
            recent_context += str(msg.content) + "\n"
        
        # Also check memory conversations
        if state.memory.session.get("conversations"):
            recent_convos = state.memory.session["conversations"][-3:]
            for convo in recent_convos:
                if "response" in convo:
                    recent_context += convo["response"] + "\n"
        
        # Parse test errors to find file names (e.g., "tests/test_tasks.py:85")
        import re
        test_error_files = re.findall(r'([\w/]+\.py):(\d+)', recent_context)
        if test_error_files:
            # Found files mentioned in test errors - use those
            unique_files = list(dict.fromkeys([f[0] for f in test_error_files]))  # Remove duplicates, keep order
            state.target_files = unique_files[:3]
            print(f"[DEBUG] Detected test error in files: {state.target_files}")
        else:
            # Fall back to LLM selection
            llm = ChatOpenAI(
                model="deepseek-chat",
                openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
                openai_api_base="https://api.deepseek.com",
                temperature=0
            )
            context_info = f"Recent context:\n{recent_context[:500]}\n\n" if recent_context else ""
            prompt = f"{context_info}Available files:\n{chr(10).join(files)}\n\nEdit request: {user_msg}\n\nWhich files need editing? Return comma-separated list."
            response = llm.invoke([SystemMessage(content=prompt)])
            selected = [f.strip() for f in response.content.split(",") if f.strip() in files]
            state.target_files = selected[:3]  # Limit to 3 files
    
    # Read files and add line numbers for LLM
    file_contents_with_lines = {}
    for filepath in state.target_files:
        content = await mcp_adapter.read_file(filepath)
        state.memory.add_file(filepath, content)
        
        # Add line numbers for LLM
        lines = content.split("\n")
        numbered_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
        file_contents_with_lines[filepath] = "\n".join(numbered_lines)
    
    # Build context with line numbers
    context_parts = []
    for filepath in state.target_files:
        context_parts.append(f"# File: {filepath}\n{file_contents_with_lines[filepath]}")
    context_with_lines = "\n\n".join(context_parts)
    
    # Generate edit plan
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com",
        temperature=0
    )
    
    prompt = SystemMessage(content=(
        f"Generate line-by-line edits for: {user_msg}\n\n"
        f"Code with line numbers:\n{context_with_lines}\n\n"
        "Return JSON with line-by-line edits:\n"
        '{{"file": "path", "edits": [{{"line": 85, "old": "                         data=json(update_data),", "new": "                         data=json.dumps(update_data),"}}]}}\n\n'
        "Rules:\n"
        "- Each edit targets ONE line number (use the line numbers shown above)\n"
        "- 'old' must match the current line EXACTLY (without the line number prefix)\n"
        "- 'new' is the replacement line (without line number prefix)\n"
        "- Look at the error message to find the exact line number\n"
        "- Focus ONLY on fixing the specific error mentioned"
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
        
        # Show brief summary (detailed view in approve node)
        summary = f"Generated {len(edit_plan.get('edits', []))} edits for {edit_plan['file']}"
        state.messages.append(AIMessage(content=summary))
        
    except Exception as e:
        state.messages.append(AIMessage(content=f"Failed to generate edit plan: {e}"))
        state.pending_edits = {}
    
    state.done = True
    return state


async def apply_edits(state: AgentState) -> AgentState:
    """Apply pending line-by-line edits"""
    
    if not state.pending_edits:
        return state
    
    filepath = state.pending_edits.get("file")
    edits = state.pending_edits.get("edits", [])
    
    if not filepath or not edits:
        state.messages.append(AIMessage(content="No valid edits to apply"))
        return state
    
    # Backup via MCP
    backup = await mcp_adapter.backup_file(filepath)
    state.edit_history.append({
        "file": filepath,
        "backup": backup,
        "timestamp": str(datetime.now())
    })
    
    # Apply edits in reverse order (to maintain line numbers)
    sorted_edits = sorted(edits, key=lambda x: x.get("line", 0), reverse=True)
    applied_count = 0
    skipped_count = 0
    
    for edit in sorted_edits:
        line_num = edit.get("line", 0)
        old_code = edit.get("old", "")
        new_code = edit.get("new", "")
        
        if line_num < 1:
            skipped_count += 1
            continue
        
        # Read current content for each edit (file changes as we go)
        content = await mcp_adapter.read_file(filepath)
        lines = content.split("\n")
        
        # Validate line number
        if line_num > len(lines):
            print(f"[EDIT] Skipping line {line_num} (file has {len(lines)} lines)")
            skipped_count += 1
            continue
        
        # Validate old code matches (if provided)
        current_line = lines[line_num - 1]
        if old_code and old_code.strip() != current_line.strip():
            print(f"[EDIT] Warning: Line {line_num} doesn't match expected content")
            print(f"  Expected: {old_code[:60]}")
            print(f"  Current:  {current_line[:60]}")
            # Still apply the edit (LLM might have whitespace differences)
        
        # Apply edit
        lines[line_num - 1] = new_code
        new_content = "\n".join(lines)
        await mcp_adapter.write_file(filepath, new_content)
        applied_count += 1
        print(f"[EDIT] Line {line_num}: {old_code[:40]}... → {new_code[:40]}...")
    
    # Update memory
    final_content = await mcp_adapter.read_file(filepath)
    state.memory.add_file(filepath, final_content)
    
    state.messages.append(AIMessage(content=f"Applied {applied_count} edits to {filepath} ({skipped_count} skipped)"))
    state.pending_edits = {}
    
    state.done = True
    return state

