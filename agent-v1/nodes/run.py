"""
Run Command Node
"""
import os
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from tools.mcp_adapter import mcp_adapter


async def run_node(state: AgentState) -> AgentState:
    """Execute command"""
    
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

