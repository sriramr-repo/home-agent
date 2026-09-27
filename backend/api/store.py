from ..agent.state import AgentState

_TASK_STORE: dict[str, AgentState] = {}

def get_task(task_id: str) -> AgentState | None:
    return _TASK_STORE.get(task_id)

def save_task(state: AgentState) -> AgentState:
    _TASK_STORE[state.task_id] = state
    return state
