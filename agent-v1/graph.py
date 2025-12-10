"""
Agent Graph - Clean LangGraph implementation
"""
from langgraph.graph import StateGraph, END

from core.state import AgentState
from nodes.intent import classify_intent
from nodes.read import read_node
from nodes.edit import edit_node
from nodes.run import run_node
from nodes.undo import undo_node
from nodes.profile import profile_node


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


def build_graph():
    """Build the agent graph"""
    
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("intent", classify_intent)
    graph.add_node("read", read_node)
    graph.add_node("edit", edit_node)
    graph.add_node("run", run_node)
    graph.add_node("undo", undo_node)
    graph.add_node("profile", profile_node)
    
    # Add edges
    graph.set_entry_point("intent")
    graph.add_conditional_edges("intent", route_intent)
    
    # All nodes go to END
    for node in ["read", "edit", "run", "undo", "profile"]:
        graph.add_edge(node, END)
    
    return graph.compile()

