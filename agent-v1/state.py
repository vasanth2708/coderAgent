from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, Field

from mcps.memory_mcp import load_memory


class AgentState(BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    intent: Optional[Literal["read", "edit", "run_command", "profile", "undo"]] = None
    target_files: List[str] = Field(default_factory=list)
    pending_edits: Dict[str, Any] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=load_memory)
    done: bool = False
    session_context: Dict[str, Any] = Field(default_factory=lambda: {
        "read_files": [],
        "file_contents": {},
        "conversation_history": []
    })
    selected_command: Optional[list[str]] = None
    working_memory: Dict[str, Any] = Field(default_factory=lambda: {
        "current_node": None,
        "current_step": None,
        "current_file": None,
        "retry_count": 0,
        "last_error": None,
        "feedback_history": []
    })
    edit_history: List[Dict[str, Any]] = Field(default_factory=list)


def last_user_text(state: AgentState) -> str:
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""

