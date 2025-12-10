"""
Run Command Node - Handles command execution and test running
"""
import os
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from tools.mcp_adapter import mcp_adapter


async def run_node(state: AgentState) -> AgentState:
    """
    Execute command or run tests.
    When called after apply_node, runs tests with retry logic.
    Otherwise, executes user-requested commands.
    """
    
    # Check if this is a test run after applying edits
    is_test_run = hasattr(state, '_run_tests_after_apply') and state._run_tests_after_apply
    
    if is_test_run:
        # Reset the flag
        state._run_tests_after_apply = False
        return await _run_tests_with_retry(state)
    
    # Normal command execution flow
    # Get user message
    user_msg = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break
    
    if not user_msg:
        state.messages.append(AIMessage(content="No command found."))
        state.done = True
        return state
    
    # Parse command intelligently
    lower = user_msg.lower()
    
    # Common patterns
    if "pytest" in lower or "test" in lower:
        command = ["pytest", "-xvs"]
    elif "lint" in lower or "flake8" in lower:
        command = ["flake8", "."]
    elif "python" in lower and "main" in lower:
        command = ["python3", "main.py"]
    elif lower.startswith(("python ", "python3 ")):
        # Direct python command
        command = user_msg.split()
    else:
        # Get available files first
        files = await mcp_adapter.list_files()
        
        # Use LLM to parse command with file context
        llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=0
        )
        
        files_context = "\n".join(files[:20]) if files else "No files found"
        
        prompt = SystemMessage(content=(
            f"Convert this user request to a shell command:\n'{user_msg}'\n\n"
            f"Available Python files in project:\n{files_context}\n\n"
            "Rules:\n"
            "- 'run tests' -> ['pytest', '-xvs']\n"
            "- 'run main file' -> ['python3', 'main.py']\n"
            "- 'run users file' -> ['python3', 'routes/users.py'] (use full path from available files)\n"
            "- 'run the route users file' -> ['python3', 'routes/users.py']\n"
            "- 'lint code' -> ['flake8', '.']\n\n"
            "IMPORTANT: If user mentions a file name, find the matching file from the available files list and use its full path.\n"
            "Return only the command as a JSON array of strings.\n"
            "Example: [\"python3\", \"routes/users.py\"]"
        ))
        
        try:
            response = llm.invoke([prompt])
            import json
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            command = json.loads(content)
            if not isinstance(command, list):
                command = ["echo", "Could not parse command"]
        except Exception as e:
            state.messages.append(AIMessage(content=f"Could not parse command: {e}"))
            state.done = True
            return state
    
    # Execute
    result = await mcp_adapter.run_command(command)
    
    # Format output
    output = f"Command: {' '.join(command)}\n"
    output += f"Exit code: {result['exit_code']}\n"
    
    if result.get('success'):
        output += "\n✓ Success\n"
    else:
        output += "\n✗ Failed\n"
    
    if result.get('stdout'):
        stdout = result['stdout'][:2000]
        output += f"\nOutput:\n{stdout}\n"
    
    if result.get('stderr'):
        stderr = result['stderr'][:2000]
        output += f"\nErrors:\n{stderr}\n"
    
    state.messages.append(AIMessage(content=output))
    state.done = True
    
    return state


async def _run_tests_with_retry(state: AgentState) -> AgentState:
    """
    Run tests and handle results with retry logic.
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

