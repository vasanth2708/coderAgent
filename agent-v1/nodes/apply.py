"""Apply Node"""
from datetime import datetime
from langchain_core.messages import AIMessage
from core.state import AgentState
from tools.mcp_adapter import mcp_adapter


async def apply_node(state: AgentState) -> AgentState:
    """
    Apply pending line-by-line edits after user approval.
    """
    
    if not state.pending_edits:
        state.messages.append(AIMessage(content="No edits to apply"))
        state.done = True
        return state
    
    filepath = state.pending_edits.get("file")
    edits = state.pending_edits.get("edits", [])
    
    if not filepath or not edits:
        state.messages.append(AIMessage(content="Invalid edit plan"))
        state.done = True
        return state
    
    print(f"\n→ Applying {len(edits)} edits to {filepath}...")
    
    # Backup file
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
            print(f"[APPLY] Skipping line {line_num} (file has {len(lines)} lines)")
            skipped_count += 1
            continue
        
        # Validate old code matches (if provided)
        current_line = lines[line_num - 1]
        if old_code and old_code.strip() != current_line.strip():
            print(f"[APPLY] Warning: Line {line_num} doesn't match expected content")
            print(f"  Expected: {old_code[:60]}")
            print(f"  Current:  {current_line[:60]}")
            # Still apply the edit (LLM might have whitespace differences)
        
        # Apply edit
        lines[line_num - 1] = new_code
        new_content = "\n".join(lines)
        await mcp_adapter.write_file(filepath, new_content)
        applied_count += 1
        print(f"[APPLY] ✓ Line {line_num}")
    
    # Update memory
    final_content = await mcp_adapter.read_file(filepath)
    state.memory.add_file(filepath, final_content)
    
    result_msg = f"✓ Applied {applied_count} edits to {filepath}"
    if skipped_count > 0:
        result_msg += f" ({skipped_count} skipped)"
    
    state.messages.append(AIMessage(content=result_msg))
    state.pending_edits = {}
    state.done = False  # Continue to run node for testing
    state._run_tests_after_apply = True  # Signal run_node to execute tests
    
    return state

