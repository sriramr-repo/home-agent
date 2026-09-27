from .state import AgentState


def observe_task(state: AgentState) -> AgentState:
    if state.status == "failed":
        return state
    state.status = "testing"
    if state.tool_results:
        summary = state.tool_results[-1].get("summary", "Tool executed successfully.")
        state.observations.append(f"Research tool executed successfully: {summary}")
    return state