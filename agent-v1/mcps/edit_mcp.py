import json
from langchain_core.messages import HumanMessage, SystemMessage

from mcps.execution_mcp import run_command
from mcps.filesystem_mcp import list_python_files, read_file
from config.llm_config import get_llm
from config.logger_config import get_logger
from state import AgentState

logger = get_logger()


async def plan_edits(state: AgentState, user_request: str, read_node_func=None) -> dict:
    session_files = state.session_context.get("file_contents", {})
    if not session_files and read_node_func:
        all_files = list_python_files()
        state.target_files = all_files
        state = read_node_func(state)
        session_files = state.session_context.get("file_contents", {})
    
    files_to_edit = []
    for filepath in session_files.keys():
        if any(part in user_request.lower() for part in filepath.lower().split('/')):
            files_to_edit.append(filepath)
    
    if not files_to_edit:
        files_to_edit = list(session_files.keys())[:5]
    
    logger.info(f"Editing {len(files_to_edit)} files: {files_to_edit}")
    
    file_contents = []
    for f in files_to_edit:
        try:
            fresh_content = read_file(f)
            state.session_context.setdefault("file_contents", {})[f] = fresh_content
            lines = fresh_content.splitlines()
            numbered_lines = "\n".join([f"{i+1:4d} | {line}" for i, line in enumerate(lines)])
            file_contents.append(f"# {f}\n{numbered_lines}")
            logger.debug(f"Read fresh content for {f} ({len(fresh_content)} chars)")
        except Exception as e:
            logger.warning(f"Could not read {f} from disk, using session cache: {e}")
            if f in session_files:
                lines = session_files[f].splitlines()
                numbered_lines = "\n".join([f"{i+1:4d} | {line}" for i, line in enumerate(lines)])
                file_contents.append(f"# {f}\n{numbered_lines}")
    
    test_context = ""
    if "test" in user_request.lower() or "fix" in user_request.lower():
        test_result = run_command(["pytest"])
        if test_result["exit_code"] != 0:
            test_context = f"\n\nTest failures:\n{test_result['stdout']}\n{test_result['stderr']}\n"
    
    preferences = state.memory.get("preferences", {})
    comment_instruction = ""
    if preferences.get("write_comments", False):
        comment_instruction = "\nIMPORTANT: Always write clear, concise comments explaining the code changes you make. Include comments near the code changes to explain what and why."
    if preferences.get("add_docstrings", False):
        comment_instruction += "\nIMPORTANT: Always add docstrings to new functions/classes you create."
    
    edit_prompt = (
        f"User request: {user_request}\n\n"
        f"{test_context}"
        "Analyze the code files below (with line numbers) and provide the necessary edits.\n\n"
        f"{comment_instruction}\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Line numbers are shown at the start of each line (e.g., '  1 | code')\n"
        "2. Use these EXACT line numbers in your edits\n"
        "3. Return ONLY a JSON array, NO explanations, NO markdown\n\n"
        "JSON format:\n"
        '[{"file": "path/to/file.py", "edits": [{"line": 10, "old": "exact old code", "new": "new code"}]}]\n\n'
        "Rules:\n"
        "- 'line': The exact line number from the file (count carefully!)\n"
        "- 'old': Copy the EXACT code from that line (can be partial for matching)\n"
        "- 'new': The complete replacement code\n"
        "- For insertions: set 'old' to empty string\n"
        "- For deletions: set 'new' to empty string\n"
        "- Be precise with line numbers - they are the primary matching mechanism\n"
    )
    
    logger.debug("Calling LLM to generate edits")
    llm = get_llm()
    msg = await llm.ainvoke([
        SystemMessage(content=edit_prompt),
        HumanMessage(content="\n\n".join(file_contents))
    ])
    
    logger.info(f"Generated edit plan, LLM response length: {len(msg.content)} characters")
    
    edits_data = []
    try:
        content = msg.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        logger.debug(f"Attempting to parse JSON: {content[:200]}...")
        edits_data = json.loads(content)
        if not isinstance(edits_data, list):
            edits_data = [edits_data]
        logger.info(f"Successfully parsed {len(edits_data)} edit items")
    except Exception as e:
        logger.warning(f"Failed to parse edits JSON: {e}")
        logger.debug(f"Raw content: {msg.content[:500]}")
        edits_data = [{"file": f, "edits": []} for f in files_to_edit]
    
    total_edits = sum(len(item.get("edits", [])) for item in edits_data if isinstance(item, dict))
    
    return {
        "edits": edits_data,
        "files": files_to_edit,
        "plan": msg.content,
        "total_edits": total_edits
    }

