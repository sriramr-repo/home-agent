from langgraph.graph import StateGraph, END
from .state import AgentState
from .planner import plan_task
from .executor import execute_task
from .observer import observe_task
from .verifier import verify_task


def _router(state: AgentState) -> str:
    if state.status in {"completed", "failed", "verifying", "awaiting_approval"}:
        return "verifier"
    return "executor"

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("planner", plan_task)
    g.add_node("executor", execute_task)
    g.add_node("observer", observe_task)
    g.add_node("verifier", verify_task)
    g.set_entry_point("planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges("executor", _router, {"executor": "executor", "verifier": "verifier"})
    g.add_edge("observer", "verifier")
    g.add_edge("verifier", END)
    return g.compile()