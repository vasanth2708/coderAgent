"""Agent State"""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage


class AgentState(BaseModel):
    """Agent state with all necessary fields"""
    
    # Messages
    messages: List[BaseMessage] = Field(default_factory=list)
    
    # Intent and routing
    intent: Optional[Literal["read", "edit", "run", "profile", "undo"]] = None
    
    # File operations
    target_files: List[str] = Field(default_factory=list)
    pending_edits: Dict[str, Any] = Field(default_factory=dict)
    
    # Memory (injected, not serialized)
    memory: Any = None
    
    # Status
    done: bool = False
    error: Optional[str] = None
    
    # Edit history for undo
    edit_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Approval and retry logic
    awaiting_approval: bool = False
    user_approved: bool = False
    retry_count: int = 0
    max_retries: int = 3
    last_test_result: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True

