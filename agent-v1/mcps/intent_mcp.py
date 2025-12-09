from langchain_core.messages import HumanMessage, SystemMessage

from config.llm_config import get_llm
from config.logger_config import get_logger
from mcps.memory_mcp import update_preferences_from_text
from state import AgentState

logger = get_logger()


async def classify_intent(state: AgentState, user_text: str) -> str:
    if update_preferences_from_text(state.memory, user_text):
        return "profile"
    
    sys = SystemMessage(
        content=(
            "Choose intent: read | edit | run_command | profile | undo.\n\n"
            "- read: user wants to understand, see, or view code (e.g., 'what does this do?', 'show me the code', 'explain')\n"
            "- edit: user wants to modify, fix, add, or write code (e.g., 'add a function', 'fix the bug', 'change this', 'write code')\n"
            "- run_command: user wants to execute/run a command or test (e.g., 'run tests', 'run pytest', 'run python main.py', 'run lint', 'execute tests', 'run all tests')\n"
            "  IMPORTANT: 'run tests', 'run pytest', 'test', 'run all tests' should be run_command, NOT edit\n"
            "- profile: user wants to set preferences (e.g., 'always write comments', 'add docstrings')\n"
            "- undo: user wants to revert/undo previous edits (e.g., 'undo', 'undo that', 'revert', 'that's wrong')\n\n"
            "Return only the intent word."
        )
    )
    logger.debug("Calling LLM to determine intent")
    logger.debug(f"Input: {user_text[:100]}...")
    llm = get_llm()
    msg = await llm.ainvoke([sys, HumanMessage(content=user_text)])
    logger.debug(f"Response: {msg.content}")
    out = msg.content.lower().strip()
    user_lower = user_text.lower()
    
    if any(word in user_lower for word in ["undo", "revert", "rollback", "that's wrong", "that was wrong"]):
        return "undo"
    
    if user_lower.startswith("run ") or user_lower.startswith("execute "):
        if any(word in user_lower for word in ["write", "create", "add", "function"]) and "test" not in user_lower:
            return "edit"
        return "run_command"
    
    if user_lower in ["test", "tests", "run tests", "run test"] or user_lower.startswith("test ") or "run test" in user_lower:
        return "run_command"
    
    if "undo" in out:
        return "undo"
    elif "run_command" in out:
        return "run_command"
    elif "run" in out:
        if any(word in user_lower for word in ["write", "create", "add", "function", "code"]) and "test" not in user_lower:
            return "edit"
        return "run_command"
    elif "test" in out and ("run" in user_lower or "execute" in user_lower):
        return "run_command"
    elif "edit" in out or "add" in out or "fix" in out or "write" in out or "create" in out:
        return "edit"
    elif "profile" in out:
        return "profile"
    elif "read" in out:
        return "read"
    
    return "read"

