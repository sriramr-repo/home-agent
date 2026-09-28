from __future__ import annotations

import logging
from langgraph.graph import END, StateGraph

from .state import AgentState
from .planner import plan_task
from .executor import execute_task
from .verifier import verify_task

from ..memory.chronicle import log_event, log_pending_mutation

logger = logging.getLogger("muse.agent")


def plan_with_logging(state: AgentState) -> AgentState:
    st = plan_task(state)
    log_event(st, "planner")
    return st


def sentinel_node(state: AgentState) -> AgentState:
    if state.status in {"completed", "failed", "awaiting_approval"}:
        return state
    if state.pending_action:
        logger.info("sentinel firewall gating pending_action task_id=%s", state.task_id)
        if state.user_approval is None:
            state.status = "awaiting_approval"
        elif state.user_approval is False:
            state.user_approval = None
            state.status = "executing"
            state.messages.append({"role": "tool", "tool_name": "sentinel", "content": "Tool execution explicitly denied by user."})
        elif state.user_approval is True:
            state.user_approval = None
            state.status = "executing"
    log_event(state, "sentinel")
    return state


def execute_with_logging(state: AgentState) -> AgentState:
    st = execute_task(state)
    log_event(st, "engineer")
    return st


def verify_with_logging(state: AgentState) -> AgentState:
    st = verify_task(state)
    log_event(st, "verifier")
    return st


def _router(state: AgentState) -> str:
    # Frozen by the sentinel: stop the thread, do not fall through to a worker.
    if state.status == "awaiting_approval":
        return END
    if state.status in {"completed", "failed", "verifying"}:
        return "verifier"
    return "engineer"


def build_multi_agent_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", plan_with_logging)
    g.add_node("sentinel", sentinel_node)
    g.add_node("engineer", execute_with_logging)
    g.add_node("verifier", verify_with_logging)

    g.set_entry_point("planner")
    g.add_edge("planner", "sentinel")
    g.add_conditional_edges(
        "sentinel",
        _router,
        {"engineer": "engineer", "verifier": "verifier", END: END},
    )
    g.add_edge("engineer", "sentinel")
    g.add_edge("verifier", END)
    return g.compile()
