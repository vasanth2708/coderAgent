"""
Read Node - Answer questions about code
"""
import os
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.state import AgentState
from tools.mcp_adapter import mcp_adapter


async def read_node(state: AgentState) -> AgentState:
    """Read files and answer question"""
    
    # Get user question
    user_msg = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            user_msg = msg.content
            break
    
    if not user_msg:
        state.messages.append(AIMessage(content="No question found."))
        state.done = True
        return state
    
    # Select files to read
    if not state.target_files:
        files = await mcp_adapter.list_files()
        # Use DeepSeek to select relevant files
        llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=0
        )
        prompt = f"Available files:\n{chr(10).join(files)}\n\nQuestion: {user_msg}\n\nWhich files are relevant? Return comma-separated list."
        response = llm.invoke([SystemMessage(content=prompt)])
        selected = [f.strip() for f in response.content.split(",") if f.strip() in files]
        state.target_files = selected[:5]  # Limit to 5 files
    
    # Read files
    for filepath in state.target_files:
        if filepath not in state.memory.session["files"]:
            content = await mcp_adapter.read_file(filepath)
            state.memory.add_file(filepath, content)
    
    # Check cache
    code_hash = state.memory.compute_hash(state.memory.session["files"])
    cached = state.memory.get_cached(code_hash, user_msg)
    if cached:
        state.messages.append(AIMessage(content=cached))
        state.done = True
        return state
    
    # Generate answer
    context = state.memory.get_context(state.target_files)
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com",
        temperature=0
    )
    
    prompt = SystemMessage(content=(
        f"Answer the user's question based on the code provided.\n\n{context}"
    ))
    
    response = llm.invoke([prompt, HumanMessage(content=user_msg)])
    answer = response.content
    
    # Cache and store
    state.memory.cache_response(code_hash, user_msg, answer)
    state.memory.add_conversation(user_msg, answer)
    state.messages.append(AIMessage(content=answer))
    state.done = True
    
    return state

