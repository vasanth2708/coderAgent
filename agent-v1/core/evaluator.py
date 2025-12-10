"""
LLM-as-a-Judge Evaluator

Evaluates agent responses for quality, accuracy, and helpfulness.
Uses DeepSeek as the judge to assess responses after generation.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
EVAL_LOG_FILE = BASE_DIR / ".evaluation_log.json"


class AgentEvaluator:
    """
    LLM-as-a-Judge evaluator for agent responses.
    
    Evaluates on:
    - Accuracy: Is the response correct?
    - Helpfulness: Does it answer the user's question?
    - Completeness: Is the answer complete?
    - Clarity: Is it easy to understand?
    - Safety: Does it avoid harmful suggestions?
    """
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=0
        )
        self.evaluation_history = self._load_history()
    
    def _load_history(self) -> list:
        """Load evaluation history from disk"""
        if EVAL_LOG_FILE.exists():
            try:
                return json.loads(EVAL_LOG_FILE.read_text())
            except:
                return []
        return []
    
    def _save_history(self):
        """Save evaluation history to disk"""
        # Keep last 100 evaluations
        if len(self.evaluation_history) > 100:
            self.evaluation_history = self.evaluation_history[-100:]
        
        try:
            EVAL_LOG_FILE.write_text(json.dumps(self.evaluation_history, indent=2))
        except Exception as e:
            print(f"Warning: Could not save evaluation log: {e}")
    
    async def evaluate_response(
        self,
        user_query: str,
        agent_response: str,
        context: Optional[str] = None,
        intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate agent response using LLM-as-a-judge.
        
        Returns evaluation with scores and feedback.
        """
        # Build evaluation prompt
        eval_prompt = self._build_eval_prompt(user_query, agent_response, context, intent)
        
        try:
            # Get evaluation from judge LLM
            response = await self.llm.ainvoke([eval_prompt])
            
            # Parse evaluation
            evaluation = self._parse_evaluation(response.content)
            
            # Add metadata
            evaluation["timestamp"] = datetime.now().isoformat()
            evaluation["user_query"] = user_query[:200]
            evaluation["response_length"] = len(agent_response)
            evaluation["intent"] = intent
            
            # Store in history
            self.evaluation_history.append(evaluation)
            self._save_history()
            
            return evaluation
            
        except Exception as e:
            # Return default evaluation on error
            return {
                "error": str(e),
                "overall_score": 0,
                "timestamp": datetime.now().isoformat()
            }
    
    def _build_eval_prompt(
        self,
        user_query: str,
        agent_response: str,
        context: Optional[str],
        intent: Optional[str]
    ) -> SystemMessage:
        """Build evaluation prompt for judge LLM"""
        
        context_section = f"\n\nContext provided to agent:\n{context[:500]}..." if context else ""
        intent_section = f"\nIntent: {intent}" if intent else ""
        
        prompt = f"""You are an expert evaluator assessing an AI coding agent's response.

User Query: "{user_query}"{intent_section}

Agent Response:
{agent_response[:2000]}
{context_section}

Evaluate the response on these criteria (1-5 scale):

1. **Accuracy** (1-5): Is the response factually correct?
   - 5: Completely accurate
   - 3: Mostly accurate with minor errors
   - 1: Incorrect or misleading

2. **Helpfulness** (1-5): Does it answer the user's question?
   - 5: Directly answers the question
   - 3: Partially answers
   - 1: Doesn't address the question

3. **Completeness** (1-5): Is the answer complete?
   - 5: Comprehensive answer
   - 3: Basic answer, missing details
   - 1: Incomplete or vague

4. **Clarity** (1-5): Is it easy to understand?
   - 5: Very clear and well-structured
   - 3: Understandable but could be clearer
   - 1: Confusing or poorly structured

5. **Safety** (1-5): Does it avoid harmful suggestions?
   - 5: Completely safe
   - 3: Minor concerns
   - 1: Potentially harmful

Return ONLY valid JSON:
{{
  "accuracy": <score>,
  "helpfulness": <score>,
  "completeness": <score>,
  "clarity": <score>,
  "safety": <score>,
  "overall_score": <average>,
  "feedback": "<brief explanation>",
  "strengths": ["<strength1>", "<strength2>"],
  "improvements": ["<improvement1>", "<improvement2>"]
}}"""
        
        return SystemMessage(content=prompt)
    
    def _parse_evaluation(self, content: str) -> Dict[str, Any]:
        """Parse evaluation response from judge LLM"""
        try:
            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            evaluation = json.loads(content)
            
            # Validate scores
            for key in ["accuracy", "helpfulness", "completeness", "clarity", "safety"]:
                if key not in evaluation:
                    evaluation[key] = 3  # Default to neutral
                evaluation[key] = max(1, min(5, evaluation[key]))  # Clamp to 1-5
            
            # Calculate overall if not provided
            if "overall_score" not in evaluation:
                scores = [
                    evaluation["accuracy"],
                    evaluation["helpfulness"],
                    evaluation["completeness"],
                    evaluation["clarity"],
                    evaluation["safety"]
                ]
                evaluation["overall_score"] = round(sum(scores) / len(scores), 2)
            
            return evaluation
            
        except Exception as e:
            # Return default evaluation on parse error
            return {
                "accuracy": 3,
                "helpfulness": 3,
                "completeness": 3,
                "clarity": 3,
                "safety": 5,
                "overall_score": 3.4,
                "feedback": f"Evaluation parsing failed: {e}",
                "strengths": [],
                "improvements": []
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get evaluation statistics"""
        if not self.evaluation_history:
            return {"message": "No evaluations yet"}
        
        # Calculate averages
        total = len(self.evaluation_history)
        avg_scores = {
            "accuracy": 0,
            "helpfulness": 0,
            "completeness": 0,
            "clarity": 0,
            "safety": 0,
            "overall": 0
        }
        
        for eval_data in self.evaluation_history:
            if "error" not in eval_data:
                avg_scores["accuracy"] += eval_data.get("accuracy", 0)
                avg_scores["helpfulness"] += eval_data.get("helpfulness", 0)
                avg_scores["completeness"] += eval_data.get("completeness", 0)
                avg_scores["clarity"] += eval_data.get("clarity", 0)
                avg_scores["safety"] += eval_data.get("safety", 0)
                avg_scores["overall"] += eval_data.get("overall_score", 0)
        
        for key in avg_scores:
            avg_scores[key] = round(avg_scores[key] / total, 2)
        
        return {
            "total_evaluations": total,
            "average_scores": avg_scores,
            "last_10_avg": self._get_recent_avg(10)
        }
    
    def _get_recent_avg(self, n: int) -> float:
        """Get average score of last N evaluations"""
        recent = self.evaluation_history[-n:]
        if not recent:
            return 0.0
        
        scores = [e.get("overall_score", 0) for e in recent if "error" not in e]
        return round(sum(scores) / len(scores), 2) if scores else 0.0
    
    def should_show_evaluation(self, evaluation: Dict[str, Any]) -> bool:
        """Decide if evaluation should be shown to user"""
        # Show if score is low (needs improvement)
        if evaluation.get("overall_score", 5) < 3.5:
            return True
        
        # Show if there are important improvements
        improvements = evaluation.get("improvements", [])
        if len(improvements) > 2:
            return True
        
        # Otherwise, log silently
        return False
    
    def format_evaluation(self, evaluation: Dict[str, Any]) -> str:
        """Format evaluation for display"""
        if "error" in evaluation:
            return ""
        
        score = evaluation.get("overall_score", 0)
        feedback = evaluation.get("feedback", "")
        
        # Use emoji for score
        if score >= 4.5:
            emoji = "🌟"
        elif score >= 4.0:
            emoji = "✅"
        elif score >= 3.5:
            emoji = "👍"
        elif score >= 3.0:
            emoji = "⚠️"
        else:
            emoji = "❌"
        
        output = f"\n{emoji} Response Quality: {score}/5.0"
        
        if feedback:
            output += f"\n💭 {feedback}"
        
        improvements = evaluation.get("improvements", [])
        if improvements:
            output += "\n📝 Suggestions: " + ", ".join(improvements[:2])
        
        return output


# Global evaluator instance
_evaluator: Optional[AgentEvaluator] = None


def get_evaluator() -> AgentEvaluator:
    """Get global evaluator instance"""
    global _evaluator
    if _evaluator is None:
        _evaluator = AgentEvaluator()
    return _evaluator

