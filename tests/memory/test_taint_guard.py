from backend.agent.state import AgentState
from backend.memory.chronicle import log_event, rehydrate_and_replay_task
from backend.tools.registry import tenant_root
import json


def test_taint_guard_on_interrupted_mutation():
    user_id = "taintuser"
    project_id = "taintproj"
    state = AgentState(
        user_id=user_id,
        project_id=project_id,
        task_id="taint-task-1",
        objective="Taint test",
        status="executing",
    )

    # Log normal event first
    log_event(state, "planner")

    # Simulate a crash mid-mutation by appending a pending_mutation record directly
    root = tenant_root(user_id, project_id)
    chronicle_file = root / "chronicle.jsonl"
    pending_event = {
        "user_id": user_id,
        "project_id": project_id,
        "task_id": "taint-task-1",
        "node_name": "engineer",
        "mutation_phase": "pending_mutation",
        "status": "executing",
        "current_step": 1,
        "objective": "Taint test",
        "messages": [],
        "tool_calls": [],
        "tool_results": [],
        "total_execution_time": 1.0,
        "compacted_turns_count": 0,
    }
    with chronicle_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(pending_event) + "\n")

    # Rehydrate and verify taint status
    rehydrated = rehydrate_and_replay_task(user_id, project_id)
    assert rehydrated is not None
    assert rehydrated.workspace_taint_status == "interrupted_execution"
