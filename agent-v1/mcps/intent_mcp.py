from langchain_core.messages import HumanMessage, SystemMessage

from mcps.llm_config import get_llm
from mcps.logger_config import get_logger
from mcps.memory_mcp import update_preferences_from_text
from state import AgentState

logger = get_logger()


async def classify_intent(state: AgentState, user_text: str) -> str:
    if update_preferences_from_text(state.memory, user_text):
        return "profile"
    
    sys = SystemMessage(
        content=(
            "Choose intent: read | edit | run_tests | profile.\n"
            "Return only the intent word."
        )
    )
    logger.debug("Calling LLM to determine intent")
    logger.debug(f"Input: {user_text[:100]}...")
    llm = get_llm()
    msg = await llm.ainvoke([sys, HumanMessage(content=user_text)])
    logger.debug(f"Response: {msg.content}")
    out = msg.content.lower()
    user_lower = user_text.lower()
    
    # Priority: fix/edit/add > test > profile > read
    # Check user text first for "fix" to handle auto-fix loop messages
    if "fix" in user_lower or "edit" in user_lower or "add" in user_lower:
        return "edit"
    elif "fix" in out or "edit" in out or "add" in out:
        return "edit"
    elif "test" in out or "test" in user_lower:
        # Only route to run_tests if it's explicitly about running tests, not fixing tests
        if "run" in user_lower or "run" in out or "execute" in user_lower:
            return "run_tests"
        # If it says "fix tests" or similar, it should be edit
        if "fix" not in user_lower:
            return "run_tests"
    elif "profile" in out:
        return "profile"
    
    return "read"

