"""
Profile Node - Manage user preferences
"""
from langchain_core.messages import AIMessage, HumanMessage
from core.state import AgentState


def profile_node(state: AgentState) -> AgentState:
    """Update user preferences"""
    
    # Get user message
    user_msg = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break
    
    if not user_msg:
        state.done = True
        return state
    
    # Extract preferences
    lower = user_msg.lower()
    prefs = state.memory.persistent["preferences"]
    
    if "comment" in lower:
        prefs["add_comments"] = "always" in lower or "yes" in lower
    if "docstring" in lower:
        prefs["add_docstrings"] = "always" in lower or "yes" in lower
    if "type" in lower and "hint" in lower:
        prefs["add_type_hints"] = "always" in lower or "yes" in lower
    
    state.memory.save()
    
    state.messages.append(AIMessage(content=f"Updated preferences: {prefs}"))
    state.done = True
    
    return state

