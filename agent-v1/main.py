"""Main Entry Point"""
import asyncio
import os
from langchain_core.messages import AIMessage, HumanMessage

from core.memory import Memory
from core.state import AgentState
from graph import build_graph
from mcp.client import initialize_mcp
from tools.mcp_adapter import mcp_adapter


def _preserve_state(old_state: AgentState, result) -> AgentState:
    """Preserve state across graph invocations"""
    if isinstance(result, dict):
        # Preserve memory
        result['memory'] = old_state.memory
        # Preserve edit history
        if hasattr(old_state, 'edit_history'):
            result['edit_history'] = old_state.edit_history
        # Preserve retry count
        if hasattr(old_state, 'retry_count'):
            result['retry_count'] = old_state.retry_count
        return AgentState(**result)
    return result


async def main():
    """Main agent loop"""
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("Error: DEEPSEEK_API_KEY not set")
        print("Get your key at: https://platform.deepseek.com/")
        return
    
    # Initialize MCP
    print("Initializing MCP servers...")
    mcp_client = await initialize_mcp()
    mcp_adapter.set_mcp_client(mcp_client)
    
    # Initialize
    memory = Memory()
    graph = build_graph()
    
    print("\nAI Coding Agent (DeepSeek-Powered)")
    print("Type 'exit' or 'quit' to stop")
    print("-" * 50)
    
    # Persistent state across requests
    state = AgentState(messages=[], memory=memory)
    
    while True:
        # Get user input
        user_input = input("\nYou> ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() in ["exit", "quit", "q"]:
            print("\nGoodbye!")
            # Cleanup MCP servers
            if mcp_client:
                mcp_client.stop_all()
            break
        
        # Check if we're handling approval
        if state.awaiting_approval and user_input.lower() in ["approve", "yes", "y"]:
            # User approved - continue graph execution with apply node
            state.user_approved = True
            state.awaiting_approval = False
            state.done = False
            
            # Continue from apply node
            from nodes.apply import apply_node
            from nodes.run import run_node
            
            print("\n→ User approved. Applying edits...")
            state = await apply_node(state)
            
            # Run tests (run_node will detect _run_tests_after_apply flag)
            state = await run_node(state)
            
            # If tests failed and retry needed, continue the loop
            while not state.done and state.retry_count <= state.max_retries:
                print(f"\n[RETRY {state.retry_count}/{state.max_retries}] Re-running graph for fix...")
                result = await graph.ainvoke(state)
                state = _preserve_state(state, result)
                
                # Print response
                if state.messages:
                    last_msg = state.messages[-1]
                    if hasattr(last_msg, 'content'):
                        print(f"Agent> {last_msg.content}\n")
                
                # If awaiting approval again, break to get user input
                if state.awaiting_approval:
                    break
                
                # If edits were generated and approved (in retry), apply and test
                if state.pending_edits and not state.awaiting_approval:
                    state = await apply_node(state)
                    state = await run_node(state)
            
            continue
        
        elif state.awaiting_approval and user_input.lower() in ["reject", "no", "n"]:
            # User rejected
            print("\nEdits rejected. Clearing pending edits.")
            state.pending_edits = {}
            state.awaiting_approval = False
            state.messages.append(AIMessage(content="Edits rejected by user"))
            continue
        
        # Add user message to state
        state.messages.append(HumanMessage(content=user_input))
        state.done = False  # Reset done flag
        state.retry_count = 0  # Reset retry count for new request
        
        # Run graph
        try:
            result = await graph.ainvoke(state)
            
            # Preserve state across invocation
            state = _preserve_state(state, result)
            
            # Print agent response
            if state.messages:
                last_msg = state.messages[-1]
                if hasattr(last_msg, 'content'):
                    print(f"{last_msg.content}\n")
            
            if state.error:
                print(f"Error> {state.error}\n")
            
            # Store conversation in memory
            if state.messages:
                last_msg = state.messages[-1]
                if hasattr(last_msg, 'content'):
                    memory.add_conversation(user_input, last_msg.content)
        
        except Exception as e:
            error_msg = str(e)
            print(f"\nError: {error_msg}")
            memory.add_conversation(user_input, f"Error: {error_msg}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

