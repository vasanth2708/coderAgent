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
            "Choose intent: read | edit | run_command | profile.\n"
            "- read: user wants to understand or see code\n"
            "- edit: user wants to modify, fix, or add code\n"
            "- run_command: user wants to run a command\n"
                "like 'run pytest' or 'run curl' or 'run python file.py' or 'run lint' or 'run black' or 'run ruff'"
                "like 'run pytest' or 'run curl' or 'run python file.py'"
            "- profile: user wants to set preferences\n"
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
    
    # Priority: fix/edit/add > run/execute > test > profile > read
    # Check user text first for "fix" to handle auto-fix loop messages
    if "fix" in user_lower or "edit" in user_lower or "add" in user_lower:
        return "edit"
    elif "fix" in out or "edit" in out or "add" in out:
        return "edit"
    # Check for run/execute commands (including "run main file", "run python file.py", etc.)
    elif "run" in user_lower or "execute" in user_lower or "run_command" in out:
        # If it says "fix" or "edit" along with "run", it's still edit
        if "fix" not in user_lower and "edit" not in user_lower:
            return "run_command"
    elif "test" in out or "test" in user_lower:
        # Only route to run_command if it's explicitly about running tests, not fixing tests
        if "run" in user_lower or "run" in out or "execute" in user_lower:
            return "run_command"
        # If it says "fix tests" or similar, it should be edit
        if "fix" not in user_lower:
            return "run_command"
    elif "profile" in out:
        return "profile"
    
    return "read"

