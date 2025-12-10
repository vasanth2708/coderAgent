"""Agent Graph"""
from langgraph.graph import StateGraph, END

from core.state import AgentState
from nodes.intent import classify_intent
from nodes.read import read_node
from nodes.edit import edit_node
from nodes.run import run_node
from nodes.undo import undo_node
from nodes.profile import profile_node
from nodes.approve import approve_node
from nodes.apply import apply_node
from nodes.evaluator import evaluator_node


def route_intent(state: AgentState) -> str:
    """Route based on intent"""
    intent_map = {
        "read": "read",
        "edit": "edit",
        "run": "run",
        "undo": "undo",
        "profile": "profile"
    }
    return intent_map.get(state.intent, "read")


def route_after_edit(state: AgentState) -> str:
    """Route after edit node - go to approve if edits were generated"""
    if state.pending_edits:
        return "approve"
    return END


def route_after_apply(state: AgentState) -> str:
    """Route after apply node - go to run node for testing"""
    return "run"


def route_after_run_tests(state: AgentState) -> str:
    """Route after run node (when running tests) - retry edit if tests failed and retries remain"""
    if state.done:
        # Tests passed or max retries reached
        return END
    else:
        # Tests failed, retry by going back to intent (which will route to edit)
        return "intent"


def build_graph():
    """Build the agent graph with approval, retry, and parallel evaluation"""
    
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("intent", classify_intent)
    graph.add_node("read", read_node)
    graph.add_node("edit", edit_node)
    graph.add_node("approve", approve_node)
    graph.add_node("apply", apply_node)
    graph.add_node("run", run_node)
    graph.add_node("undo", undo_node)
    graph.add_node("profile", profile_node)
    graph.add_node("evaluator", evaluator_node)  # Parallel evaluation
    
    # Add edges
    graph.set_entry_point("intent")
    graph.add_conditional_edges("intent", route_intent)
    
    # Edit flow: edit → approve → (wait for user) → apply → run (tests) → (retry if needed)
    graph.add_conditional_edges("edit", route_after_edit)
    graph.add_edge("approve", END)  # Pause for user approval
    graph.add_conditional_edges("apply", route_after_apply)
    
    # Run node needs conditional routing:
    # - If it's running tests (after apply), use route_after_run_tests
    # - Otherwise, go to evaluator
    # We'll handle this by checking state.done in a new routing function
    def route_run(state: AgentState) -> str:
        """Route from run node - check if it was a test run or normal command"""
        if hasattr(state, '_run_tests_after_apply') and not state.done:
            # Tests failed, need to retry
            return "intent"
        elif state.done:
            # Normal command or tests passed
            return "evaluator"
        else:
            # Shouldn't happen, but default to evaluator
            return "evaluator"
    
    graph.add_conditional_edges("run", route_run)
    
    # Other nodes go to evaluator before END
    # Note: In LangGraph, we can't truly run in parallel, but we can chain evaluator before END
    # The evaluator is designed to be fast and non-blocking
    for node in ["read", "undo", "profile"]:
        graph.add_edge(node, "evaluator")
    
    # Evaluator always goes to END
    graph.add_edge("evaluator", END)
    
    return graph.compile()

