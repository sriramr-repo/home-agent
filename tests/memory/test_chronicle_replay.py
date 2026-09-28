from backend.agent.state import AgentState
from backend.memory.chronicle import log_event, rehydrate_and_replay_task


def test_chronicle_roundtrip():
    state = AgentState(
        user_id="testuser",
        project_id="testproj",
        task_id="task-replay-1",
        objective="Rehydrate test",
        status="running",
        current_step=2,
        total_execution_time=3.5,
        compacted_turns_count=1,
    )
    state.messages.append({"role": "user", "content": "Hello"})
    state.tool_calls.append({"name": "list_files", "arguments": {}})

    log_event(state, "planner")
    log_event(state, "engineer")

    replayed = rehydrate_and_replay_task("testuser", "testproj")
    assert replayed is not None
    assert replayed.task_id == state.task_id
    assert replayed.objective == state.objective
    assert replayed.current_step == state.current_step
    assert replayed.total_execution_time == state.total_execution_time
    assert replayed.compacted_turns_count == state.compacted_turns_count
    assert len(replayed.messages) == len(state.messages)
    assert len(replayed.tool_calls) == len(state.tool_calls)


def test_chronicle_missing_returns_none():
    assert rehydrate_and_replay_task("ghostuser", "ghostproj") is None
