import time
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from mcps.execution_mcp import read_files_parallel
from mcps.filesystem_mcp import cache_file, get_cached_file, read_file
from config.llm_config import get_llm
from config.logger_config import get_logger
from mcps.memory_mcp import cache_response, compute_code_hash, get_cached_response
from state import AgentState

logger = get_logger()


async def retrieve_context(state: AgentState, user_question: str) -> tuple:
    files_to_read = []
    cached_count = 0
    session_cached = 0
    
    for f in state.target_files:
        if f in state.session_context.get("file_contents", {}):
            session_cached += 1
            cached_content = state.session_context["file_contents"][f]
            files_to_read.append((f, cached_content))
            logger.debug(f"Using session-cached {f}")
        elif get_cached_file(f):
            cached_content = get_cached_file(f)
            cached_count += 1
            files_to_read.append((f, cached_content))
        else:
            files_to_read.append((f, None))
    
    if session_cached > 0:
        logger.info(f"{session_cached}/{len(state.target_files)} files from session cache")
    if cached_count > 0:
        logger.info(f"{cached_count}/{len(state.target_files)} files from file cache")
    
    files_to_fetch = [(f, cached) for f, cached in files_to_read if cached is None]
    if files_to_fetch:
        start_time = time.time()
        file_paths = [f for f, _ in files_to_fetch]
        results = read_files_parallel(file_paths, [None] * len(file_paths))
        read_time = time.time() - start_time
        logger.info(f"Parallel read completed in {read_time:.3f}s")
    else:
        results = []
        logger.info("All files from cache, no disk I/O needed")
    
    content = []
    total_size = 0
    file_contents_map = {}
    
    for f, cached_content in files_to_read:
        if cached_content is not None and f not in [r["file"] for r in results]:
            content.append(f"# {f}\n{cached_content}")
            total_size += len(cached_content)
            file_contents_map[f] = cached_content
            logger.debug(f"Cached {f} ({len(cached_content)} chars)")
    
    for result in results:
        if result["error"]:
            logger.warning(f"Error reading {result['file']}: {result['error']}")
            content.append(f"# {result['file']}\nERROR: {result['error']}")
        else:
            content.append(f"# {result['file']}\n{result['content']}")
            total_size += result['size']
            file_contents_map[result['file']] = result['content']
            cache_file(result['file'], result['content'])
            if not result.get("cached", False):
                logger.debug(f"Read {result['file']} ({result['size']} chars)")
            else:
                logger.debug(f"Cached {result['file']} ({result['size']} chars)")
    
    state.session_context["read_files"].extend(state.target_files)
    state.session_context["read_files"] = list(set(state.session_context["read_files"]))
    state.session_context["file_contents"].update(file_contents_map)
    
    logger.info(f"Total content: {total_size} characters from {len(content)} files")
    logger.info(f"Session now has {len(state.session_context['read_files'])} files in context")
    
    current_file_contents = {}
    for filepath in state.target_files:
        try:
            current_file_contents[filepath] = read_file(filepath)
        except Exception as e:
            logger.warning(f"Could not read {filepath} for hash computation: {e}")
            if filepath in file_contents_map:
                current_file_contents[filepath] = file_contents_map[filepath]
                logger.warning(f"Using cached content for hash computation due to read error")
    
    code_hash = compute_code_hash(current_file_contents)
    logger.debug(f"Code hash computed from {len(current_file_contents)} files (fresh disk reads)")
    logger.debug(f"Code hash: {code_hash[:16]}...")
    
    cached_response_text = get_cached_response(state.memory, code_hash, user_question)
    if cached_response_text:
        print(f"→ Using cached response")
        return cached_response_text, file_contents_map
    
    logger.debug("Processing retrieved content for arbitration")
    arbitration_start = time.time()
    
    history = state.session_context.get("conversation_history", [])
    history_context = ""
    if history:
        history_context = "\n\nPrevious conversation:\n" + "\n".join([f"Q: {h['q']}\nA: {h['a'][:200]}..." for h in history[-3:]])
    
    arbitration_prompt = (
        f"Answer ONLY the user's specific question: '{user_question}'\n\n"
        "Use the provided code files to answer the question directly and concisely. "
        "Do not provide a full codebase explanation unless specifically asked. "
        "Focus on answering what was asked."
        f"{history_context}"
    )
    
    MAX_CONTEXT_LENGTH = 50000
    def truncate_context(content: str, max_length: int = MAX_CONTEXT_LENGTH) -> str:
        """Truncate content if it exceeds max_length, keeping the beginning"""
        if len(content) <= max_length:
            return content
        logger.warning(f"Context truncated from {len(content)} to {max_length} characters")
        return content[:max_length] + "\n... [truncated]"
    
    full_content = f"User question: {user_question}\n\nCode files:\n\n" + "\n\n".join(content)
    truncated_content = truncate_context(full_content)
    
    if len(truncated_content) < len(full_content):
        logger.warning(f"Content truncated from {len(full_content)} to {len(truncated_content)} characters")
    
    logger.debug("Calling LLM (arbitration agent) to answer question")
    llm = get_llm()
    msg = await llm.ainvoke([
        SystemMessage(content=truncate_context(arbitration_prompt)),
        HumanMessage(content=truncated_content)
    ])
    
    response_content = msg.content
    if len(response_content) > 10000:  # Limit cached responses
        response_content = response_content[:10000] + "... [truncated]"
    arbitration_time = time.time() - arbitration_start
    logger.info(f"Arbitration completed in {arbitration_time:.3f}s, response: {len(msg.content)} characters")
    
    cache_response(state.memory, code_hash, user_question, response_content)
    
    return msg.content, file_contents_map

