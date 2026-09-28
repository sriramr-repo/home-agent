from backend.agent.state import AgentState
from backend.memory.chronicle import log_event, log_pending_mutation, rehydrate_and_replay_task


def test_crash_mid_mutation_surfaces_taint():
    """A pending mutation with no settling event must rehydrate as tainted."""
    state = AgentState(
        user_id="chaosuser",
        project_id="chaosproj",
        task_id="chaos-task-1",
        objective="Write a file then die",
        status="executing",
        current_step=3,
        total_execution_time=2.5,
    )
    state.messages.append({"role": "user", "content": "Write a file then die"})

    log_event(state, "planner")
    # Worker announces intent to mutate, then the process never returns.
    log_pending_mutation(state, "engineer", ["write_file"])

    recovered = rehydrate_and_replay_task("chaosuser", "chaosproj")

    assert recovered is not None
    assert recovered.workspace_taint_status == "interrupted_execution"
    # Graph-critical fields survive the crash intact.
    assert recovered.task_id == state.task_id
    assert recovered.objective == state.objective
    assert recovered.current_step == state.current_step
    assert recovered.total_execution_time == state.total_execution_time
    assert len(recovered.messages) == len(state.messages)
    assert "corrupted_log" not in recovered.errors


def test_settled_mutation_leaves_workspace_clean():
    """Counterpart: a completed mutation must NOT be flagged as tainted."""
    state = AgentState(
        user_id="chaosuser",
        project_id="settledproj",
        task_id="chaos-task-2",
        objective="Write a file and finish",
        status="executing",
    )

    log_pending_mutation(state, "engineer", ["write_file"])
    state.status = "completed"
    log_event(state, "engineer")

    recovered = rehydrate_and_replay_task("chaosuser", "settledproj")

    assert recovered is not None
    assert recovered.workspace_taint_status is None
    assert recovered.status == "completed"


def test_non_mutating_tool_writes_no_pending_marker():
    """Read-only tools must not arm the taint guard."""
    state = AgentState(
        user_id="chaosuser",
        project_id="readonlyproj",
        task_id="chaos-task-3",
        objective="Just read",
        status="executing",
    )

    log_event(state, "planner")
    log_pending_mutation(state, "engineer", ["read_file", "list_files"])

    recovered = rehydrate_and_replay_task("chaosuser", "readonlyproj")

    assert recovered is not None
    assert recovered.workspace_taint_status is None
