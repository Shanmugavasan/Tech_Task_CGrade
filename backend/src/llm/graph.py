from langgraph.graph import StateGraph, START, END
from src.llm.state import ThreadTriageState
from src.llm.nodes import (
    context_merger_node,
    classification_node,
    task_extraction_node,
    priority_scoring_node,
    consolidation_node
)

def route_by_classification(state: ThreadTriageState) -> str:
    """Routes the execution path dynamically based on classification."""
    classification = state.get("classification")
    if classification == "Actionable":
        return "task_extraction"
    elif classification == "Informational":
        return "consolidation"
    # Irrelevant messages still need a concise review summary for audit and correction.
    return "consolidation"

def build_triage_graph():
    builder = StateGraph(ThreadTriageState)

    # Register Nodes
    builder.add_node("context_merger", context_merger_node)
    builder.add_node("classifier", classification_node)
    builder.add_node("task_extraction", task_extraction_node)
    builder.add_node("priority_scoring", priority_scoring_node)
    builder.add_node("consolidation", consolidation_node)

    # Edge Definitions
    builder.add_edge(START, "context_merger")
    builder.add_edge("context_merger", "classifier")

    builder.add_conditional_edges(
        "classifier",
        route_by_classification,
        {
            "task_extraction": "task_extraction",
            "consolidation": "consolidation",
            END: END
        }
    )

    builder.add_edge("task_extraction", "priority_scoring")
    builder.add_edge("priority_scoring", "consolidation")
    builder.add_edge("consolidation", END)

    return builder.compile()

triage_pipeline = build_triage_graph()