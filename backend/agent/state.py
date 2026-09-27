from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

Status = Literal[
    "initialized", "inspecting", "planning", "executing", "testing",
    "debugging", "verifying", "completed", "failed", "running",
    "awaiting_approval",
]

class AgentState(BaseModel):
    user_id: str = "local"
    project_id: str = "default"
    task_id: str
    objective: str
    repository_path: str = "."
    plan: list[str] = Field(default_factory=list)
    current_step: int = 0
    iteration_count: int = 0
    max_agent_iterations: Optional[int] = None
    model_invocations: list[dict[str, Any]] = Field(default_factory=list)
    current_step_name: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_memory: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    commands_executed: list[str] = Field(default_factory=list)
    test_results: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    verification_results: dict[str, Any] = Field(default_factory=dict)
    status: Status = "initialized"
    pending_action: Optional[dict[str, Any]] = None
    user_approval: Optional[bool] = True
    result: Optional[str] = None
    error: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
