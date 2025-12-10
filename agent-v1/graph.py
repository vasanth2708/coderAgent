"""
Agent Graph - LangGraph implementation with approval, retry, and parallel evaluation
"""
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
from nodes.test import test_node
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
    """Route after apply node - always go to test"""
    return "test"


def route_after_test(state: AgentState) -> str:
    """Route after test node - retry edit if tests failed and retries remain"""
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
    graph.add_node("test", test_node)
    graph.add_node("run", run_node)
    graph.add_node("undo", undo_node)
    graph.add_node("profile", profile_node)
    graph.add_node("evaluator", evaluator_node)  # Parallel evaluation
    
    # Add edges
    graph.set_entry_point("intent")
    graph.add_conditional_edges("intent", route_intent)
    
    # Edit flow: edit → approve → (wait for user) → apply → test → (retry if needed)
    graph.add_conditional_edges("edit", route_after_edit)
    graph.add_edge("approve", END)  # Pause for user approval
    graph.add_conditional_edges("apply", route_after_apply)
    graph.add_conditional_edges("test", route_after_test)
    
    # Other nodes go to END, but also trigger evaluator in parallel
    # Note: In LangGraph, we can't truly run in parallel, but we can chain evaluator before END
    # The evaluator is designed to be fast and non-blocking
    for node in ["read", "run", "undo", "profile"]:
        graph.add_edge(node, "evaluator")
    
    # Evaluator always goes to END
    graph.add_edge("evaluator", END)
    
    return graph.compile()

