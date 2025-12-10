"""
Main Entry Point - Clean agent execution with LLM-as-a-judge evaluation
"""
import asyncio
import os
from langchain_core.messages import HumanMessage

from core.memory import Memory
from core.state import AgentState
from core.evaluator import get_evaluator
from graph import build_graph
from mcp.client import initialize_mcp
from tools.mcp_adapter import mcp_adapter


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
    evaluator = get_evaluator()
    graph = build_graph()
    
    print("\nAI Coding Agent (DeepSeek-Powered)")
    print("Commands: 'exit' to quit, 'approve' to apply edits")
    print("-" * 50)
    
    while True:
        # Get user input
        user_input = input("\nYou: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() in ["exit", "quit", "q"]:
            # Show evaluation statistics before exit
            stats = evaluator.get_statistics()
            if "average_scores" in stats:
                print(f"\n📊 Session Statistics:")
                print(f"   Total interactions: {stats['total_evaluations']}")
                print(f"   Average quality: {stats['average_scores']['overall']}/5.0")
                print(f"   Recent (last 10): {stats['last_10_avg']}/5.0")
            
            print("\nGoodbye!")
            # Cleanup MCP servers
            if mcp_client:
                mcp_client.stop_all()
            break
        
        # Show stats command
        if user_input.lower() == "stats":
            stats = evaluator.get_statistics()
            if "average_scores" in stats:
                print(f"\n📊 Evaluation Statistics:")
                print(f"   Total: {stats['total_evaluations']} evaluations")
                print(f"   Accuracy: {stats['average_scores']['accuracy']}/5.0")
                print(f"   Helpfulness: {stats['average_scores']['helpfulness']}/5.0")
                print(f"   Completeness: {stats['average_scores']['completeness']}/5.0")
                print(f"   Clarity: {stats['average_scores']['clarity']}/5.0")
                print(f"   Overall: {stats['average_scores']['overall']}/5.0")
            else:
                print(stats.get("message", "No statistics available"))
            continue
        
        # Handle approval
        if user_input.lower() == "approve":
            # TODO: Apply pending edits
            print("Edit application not yet implemented in this clean version")
            continue
        
        # Create state
        state = AgentState(
            messages=[HumanMessage(content=user_input)],
            memory=memory
        )
        
        # Run graph
        try:
            result = await graph.ainvoke(state)
            
            # Handle result (may be dict or AgentState)
            if isinstance(result, dict):
                messages = result.get("messages", [])
                error = result.get("error")
            else:
                messages = result.messages
                error = result.error
            
            # Get response
            response = None
            intent = result.get("intent") if isinstance(result, dict) else getattr(result, "intent", None)
            
            if messages:
                last_msg = messages[-1]
                response = last_msg.content
                print(f"\nAgent: {response}")
            
            if error:
                response = f"Error: {error}"
                print(f"\n{response}")
            
            # Evaluate response quality (LLM-as-a-judge)
            if response and not error:
                context = memory.get_context(
                    result.get("target_files", []) if isinstance(result, dict) else getattr(result, "target_files", []),
                    max_chars=1000  # Brief context for evaluation
                )
                
                evaluation = await evaluator.evaluate_response(
                    user_query=user_input,
                    agent_response=response,
                    context=context,
                    intent=intent
                )
                
                # Show evaluation if score is low or has important feedback
                if evaluator.should_show_evaluation(evaluation):
                    eval_display = evaluator.format_evaluation(evaluation)
                    if eval_display:
                        print(eval_display)
            
            # Store ALL conversations in memory (success or failure)
            if response:
                memory.add_conversation(user_input, response)
        
        except Exception as e:
            error_msg = str(e)
            print(f"\nError: {error_msg}")
            # Store error conversations too
            memory.add_conversation(user_input, f"Error: {error_msg}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

