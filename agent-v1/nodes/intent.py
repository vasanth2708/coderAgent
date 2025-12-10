"""
Intent Classification Node
"""
import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState


def classify_intent(state: AgentState) -> AgentState:
    """Classify user intent from last message"""
    
    # Get last user message
    user_msg = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break
    
    if not user_msg:
        state.intent = "read"
        return state
    
    # Quick keyword matching first
    lower = user_msg.lower()
    if "undo" in lower or "revert" in lower:
        state.intent = "undo"
        return state
    
    if any(word in lower for word in ["run", "execute", "test", "pytest"]):
        state.intent = "run"
        return state
    
    if any(word in lower for word in ["prefer", "always", "setting"]):
        state.intent = "profile"
        return state
    
    # Use DeepSeek for ambiguous cases
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com",
        temperature=0
    )
    
    prompt = SystemMessage(content=(
        "Classify intent: read | edit | run | profile | undo\n\n"
        "- read: understand/view code\n"
        "- edit: modify/fix/add code\n"
        "- run: execute command/test\n"
        "- profile: set preferences\n"
        "- undo: revert changes\n\n"
        "Return only the intent word."
    ))
    
    response = llm.invoke([prompt, HumanMessage(content=user_msg)])
    intent = response.content.strip().lower()
    
    if intent in ["read", "edit", "run", "profile", "undo"]:
        state.intent = intent
    else:
        # Default to read for safety
        state.intent = "read"
    
    return state

