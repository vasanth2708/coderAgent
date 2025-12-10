"""Test Node"""
from langchain_core.messages import AIMessage, HumanMessage
from core.state import AgentState
from tools.mcp_adapter import mcp_adapter


async def test_node(state: AgentState) -> AgentState:
    """
    Run tests and handle results.
    If tests fail and retry_count < max_retries, prepare for retry.
    """
    
    # Run tests
    print("\n→ Running tests...")
    test_result = await mcp_adapter.run_command(["pytest", "-xvs"])
    state.last_test_result = test_result
    
    if test_result["success"]:
        # Tests passed!
        print("Agent> ✅ All tests passed!\n")
        state.messages.append(AIMessage(content="✅ All tests passed!"))
        state.retry_count = 0  # Reset retry count
        state.done = True
        return state
    
    # Tests failed
    print(f"Agent> ⚠️ Tests failed (attempt {state.retry_count + 1}/{state.max_retries})\n")
    
    if state.retry_count < state.max_retries:
        # Prepare for retry
        state.retry_count += 1
        
        # Add error context to messages for next edit attempt
        error_msg = (
            f"Tests failed (attempt {state.retry_count}/{state.max_retries}):\n"
            f"{test_result['stdout'][:1000]}\n"
            f"{test_result['stderr'][:500]}\n\n"
            f"Please fix the failing tests."
        )
        state.messages.append(HumanMessage(content=error_msg))
        
        # Clear pending edits and target files to force re-analysis
        state.pending_edits = {}
        state.target_files = []
        state.intent = "edit"  # Route back to edit
        state.done = False  # Continue graph execution
        
        print(f"[AUTO-RETRY] Attempt {state.retry_count}/{state.max_retries} - routing back to edit\n")
    else:
        # Max retries reached
        state.messages.append(AIMessage(
            content=f"⚠️ Tests still failing after {state.max_retries} attempts. Please review manually."
        ))
        state.retry_count = 0  # Reset for next time
        state.done = True
    
    return state

