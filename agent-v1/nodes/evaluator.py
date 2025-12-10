"""
Evaluator Node - Evaluate agent responses in parallel
"""
import os
import json
from datetime import datetime
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from core.state import AgentState


EVAL_LOG_FILE = Path(__file__).parent.parent / ".evaluation_log.json"


async def evaluator_node(state: AgentState) -> AgentState:
    """
    Evaluate the quality of the agent's response.
    Runs in parallel after output, doesn't block the main flow.
    """
    
    # Only evaluate if we have messages
    if not state.messages or len(state.messages) < 2:
        return state
    
    # Get the last user query and agent response
    user_msg = None
    agent_msg = None
    
    for msg in reversed(state.messages):
        if hasattr(msg, '__class__'):
            if msg.__class__.__name__ == "HumanMessage" and not user_msg:
                user_msg = msg.content
            elif msg.__class__.__name__ == "AIMessage" and not agent_msg:
                agent_msg = msg.content
        
        if user_msg and agent_msg:
            break
    
    if not user_msg or not agent_msg:
        return state
    
    # Skip evaluation for certain intents (e.g., approval messages)
    if state.awaiting_approval or user_msg.lower() in ["approve", "yes", "y", "reject", "no", "n"]:
        return state
    
    try:
        # Initialize LLM for evaluation
        llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=0
        )
        
        # Evaluation prompt
        eval_prompt = SystemMessage(content=(
            "You are an AI response evaluator. Rate the agent's response on a scale of 1-5.\n\n"
            "Criteria:\n"
            "- Accuracy: Does it correctly address the query?\n"
            "- Completeness: Is the response thorough?\n"
            "- Clarity: Is it easy to understand?\n"
            "- Relevance: Does it stay on topic?\n\n"
            f"User Query: {user_msg}\n\n"
            f"Agent Response: {agent_msg[:1000]}...\n\n"
            "Return JSON: {{\"score\": 1-5, \"reasoning\": \"brief explanation\"}}"
        ))
        
        response = llm.invoke([eval_prompt])
        
        # Parse evaluation
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        evaluation = json.loads(content.strip())
        
        # Log evaluation
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "intent": state.intent,
            "user_query": user_msg[:200],
            "agent_response_preview": agent_msg[:200],
            "score": evaluation.get("score", 0),
            "reasoning": evaluation.get("reasoning", ""),
            "retry_count": state.retry_count
        }
        
        # Append to log file
        logs = []
        if EVAL_LOG_FILE.exists():
            try:
                logs = json.loads(EVAL_LOG_FILE.read_text())
            except:
                logs = []
        
        logs.append(log_entry)
        
        # Keep last 100 evaluations
        if len(logs) > 100:
            logs = logs[-100:]
        
        EVAL_LOG_FILE.write_text(json.dumps(logs, indent=2))
        
        print(f"[EVALUATOR] Score: {evaluation.get('score')}/5 - {evaluation.get('reasoning', '')[:60]}...")
    
    except Exception as e:
        # Don't fail the main flow if evaluation fails
        print(f"[EVALUATOR] Evaluation failed: {e}")
    
    return state

