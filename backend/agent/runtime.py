from uuid import uuid4

from .graph import build_graph
from .state import AgentState


def run_agent(
    objective: str,
    task_id: str | None = None,
    user_id: str = "local",
    project_id: str = "default",
) -> AgentState:
    state = AgentState(
        task_id=task_id or str(uuid4()),
        user_id=user_id,
        project_id=project_id,
        objective=objective,
    )
    return AgentState.model_validate(build_graph().invoke(state))