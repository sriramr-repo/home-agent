from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...agent.runtime import run_agent
from ...agent.graph import build_graph
from ...agent.state import AgentState
from ..store import get_task, save_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    objective: str = Field(min_length=1)


@router.post("", response_model=AgentState, status_code=status.HTTP_201_CREATED)
async def create_task(request: CreateTaskRequest) -> AgentState:
    state = run_agent(request.objective)
    return save_task(state)


@router.get("/{task_id}", response_model=AgentState)
async def get_task_endpoint(task_id: str) -> AgentState:
    state = get_task(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    return state


@router.post("/{task_id}/approve", response_model=AgentState)
async def approve_task(task_id: str) -> AgentState:
    state = get_task(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    state.user_approval = True
    res = build_graph().invoke(state)
    updated = AgentState.model_validate(res)
    return save_task(updated)


@router.post("/{task_id}/deny", response_model=AgentState)
async def deny_task(task_id: str) -> AgentState:
    state = get_task(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    state.user_approval = False
    res = build_graph().invoke(state)
    updated = AgentState.model_validate(res)
    return save_task(updated)
