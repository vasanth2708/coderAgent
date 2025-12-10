"""
Undo Node - Revert last edit
"""
from langchain_core.messages import AIMessage
from core.state import AgentState
from tools.mcp_adapter import mcp_adapter


async def undo_node(state: AgentState) -> AgentState:
    """Undo last edit"""
    
    if not state.edit_history:
        state.messages.append(AIMessage(content="No edits to undo."))
        state.done = True
        return state
    
    # Get last edit
    last_edit = state.edit_history.pop()
    filepath = last_edit["file"]
    backup = last_edit["backup"]
    
    # Restore via MCP
    await mcp_adapter.restore_file(filepath, backup)
    state.memory.add_file(filepath, backup)
    
    state.messages.append(AIMessage(content=f"Reverted changes to {filepath}"))
    state.done = True
    
    return state

