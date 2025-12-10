"""
Approval Node - Handle user approval for edits
"""
from langchain_core.messages import AIMessage
from core.state import AgentState


def approve_node(state: AgentState) -> AgentState:
    """
    Present edits to user and wait for approval.
    This node sets awaiting_approval=True and returns.
    The main loop will handle getting user input.
    """
    
    if not state.pending_edits:
        state.messages.append(AIMessage(content="No edits to approve"))
        state.done = True
        return state
    
    # Show edit summary
    edit_plan = state.pending_edits
    summary = f"\n{'='*50}\n"
    summary += f"📝 EDIT PLAN for {edit_plan.get('file', 'unknown')}\n"
    summary += f"{'='*50}\n"
    
    for edit in edit_plan.get("edits", []):
        line_num = edit.get('line', '?')
        old_preview = edit.get('old', '')[:60]
        new_preview = edit.get('new', '')[:60]
        summary += f"\nLine {line_num}:\n"
        summary += f"  - {old_preview}...\n"
        summary += f"  + {new_preview}...\n"
    
    summary += f"\n{'='*50}\n"
    summary += "Type 'approve' or 'yes' to apply these edits\n"
    summary += "Type 'reject' or 'no' to cancel\n"
    summary += f"{'='*50}"
    
    state.messages.append(AIMessage(content=summary))
    state.awaiting_approval = True
    state.done = True  # Pause graph execution
    
    return state

