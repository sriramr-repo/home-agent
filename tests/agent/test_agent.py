from fastapi.testclient import TestClient
from backend.main import app
from backend.agent.state import AgentState
from backend.agent.planner import plan_task
from backend.agent.executor import execute_task
from backend.agent.runtime import run_agent

client = TestClient(app)


def test_planner():
    from unittest.mock import patch
    
    class MockPlannerModel:
        def invoke(self, messages, tools=None):
            return {"content": '{"steps": ["Inspect", "Verify"]}', "tool_calls": []}
    
    with patch("backend.agent.planner.LocalModel", return_value=MockPlannerModel()):
        state = AgentState(task_id="1", objective="Research AI agents")
        updated = plan_task(state)
    assert updated.status == "planning"
    assert len(updated.plan) > 1


def test_model_driven_execution_and_recovery():
    from unittest.mock import patch
    from backend.agent.model import ToolCall

    responses = iter([
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "README.md"})]},
        {"content": "", "tool_calls": [ToolCall("run_command", {"command": "ls"})]},
        {"content": "done", "tool_calls": []},
    ])

    class MockModel:
        def invoke(self, messages, tools=None):
            response = next(responses)
            if response["tool_calls"]:
                assert messages[-1]["role"] == "tool" if len(messages) > 2 else True
            return response

    state = AgentState(task_id="1", objective="Inspect workspace")
    with patch("backend.agent.executor.LocalModel", return_value=MockModel()):
        state = execute_task(state)
        assert state.tool_calls[-1]["name"] == "read_file"
        state = execute_task(state)
        assert state.tool_calls[-1]["name"] == "run_command"
        state = execute_task(state)
    assert state.result == "done"


def test_full_graph_success():
    from unittest.mock import patch
    from backend.agent.model import ToolCall

    calls = iter([
        {"content": "", "tool_calls": [ToolCall("run_command", {"command": "pwd"})]},
        {"content": "done", "tool_calls": []},
    ])

    class PlannerModel:
        def invoke(self, messages, tools=None):
            return {"content": '{"steps": ["Inspect", "Verify"]}', "tool_calls": []}

    class ExecutorModel:
        def invoke(self, messages, tools=None):
            return next(calls)

    with patch("backend.agent.planner.LocalModel", return_value=PlannerModel()), \
         patch("backend.agent.executor.LocalModel", return_value=ExecutorModel()):
        final = run_agent("Research AI agents")
    assert final.status == "completed"
    assert final.result == "done"


def test_full_graph_failure():
    from unittest.mock import patch
    from backend.agent.model import ToolCall

    class MockModel:
        def invoke(self, messages, tools=None):
            return {"content": "", "tool_calls": [ToolCall("run_command", {"command": "pytest --invalid"})]}

    class PlannerModel:
        def invoke(self, messages, tools=None):
            return {"content": '{"steps": ["Inspect"]}', "tool_calls": []}

    with patch("backend.agent.planner.LocalModel", return_value=PlannerModel()), \
         patch("backend.agent.executor.LocalModel", return_value=MockModel()):
        final = run_agent("Validate")
    assert final.status == "failed"
    assert final.error is not None


def test_api_tasks():
    from unittest.mock import patch
    from backend.agent.model import ToolCall

    calls = iter([
        {"content": "", "tool_calls": [ToolCall("run_command", {"command": "pwd"})]},
        {"content": "done", "tool_calls": []},
    ])

    class PlannerModel:
        def invoke(self, messages, tools=None):
            return {"content": '{"steps": ["Inspect", "Verify"]}', "tool_calls": []}

    class ExecutorModel:
        def invoke(self, messages, tools=None):
            return next(calls)

    with patch("backend.agent.planner.LocalModel", return_value=PlannerModel()), \
         patch("backend.agent.executor.LocalModel", return_value=ExecutorModel()):
        response = client.post("/tasks", json={"objective": "Research the AI agent market"})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "completed"
    assert data["objective"] == "Research the AI agent market"
    assert len(data["plan"]) > 0
    assert data["result"] is not None
