import pytest
from backend.agent.state import AgentState
from backend.agent.executor import execute_task

def test_high_risk_approval_flow():
    state = AgentState(
        task_id="t1",
        objective="run echo",
        repository_path="/tmp",
        messages=[],
        tool_calls=[],
        tool_results=[],
        observations=[],
        files_changed=[],
        commands_executed=[],
        errors=[],
        status="running",
        iteration_count=0,
        current_step=0,
        model_invocations=[],
        result=None
    )
    state.pending_action = {"name": "run_command", "arguments": {"command": "echo hi"}}
    state.user_approval = None
    res_state = execute_task(state)
    assert res_state.status == "awaiting_approval"
    assert res_state.pending_action is not None

    res_state.user_approval = False
    res_state2 = execute_task(res_state)
    assert res_state2.status == "executing"
    assert res_state2.pending_action is None
    assert "Tool execution explicitly denied by user." in res_state2.observations[-1]
