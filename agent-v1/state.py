from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from mcps.memory_mcp import load_memory


class AgentState(BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    intent: Optional[Literal["read", "edit", "run_command", "profile"]] = None
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


def last_user_text(state: AgentState) -> str:
    from langchain_core.messages import HumanMessage
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""

