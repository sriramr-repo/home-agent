from uuid import uuid4

from .graph import build_graph
from .multi_agent_graph import build_multi_agent_graph
from .state import AgentState


def run_agent(
    objective: str,
    task_id: str | None = None,
    user_id: str = "local",
    project_id: str = "default",
    use_multi_agent: bool = False,
) -> AgentState:
    state = AgentState(
        task_id=task_id or str(uuid4()),
        user_id=user_id,
        project_id=project_id,
        objective=objective,
        user_approval=None if use_multi_agent else True,
    )
    graph = build_multi_agent_graph() if use_multi_agent else build_graph()
    return AgentState.model_validate(graph.invoke(state))