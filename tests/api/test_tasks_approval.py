from fastapi.testclient import TestClient
from unittest.mock import patch
import pytest
from backend.main import app
from backend.agent.state import AgentState
from backend.api.store import save_task

client = TestClient(app)

def test_task_approval_endpoints():
    # Test GET endpoint
    state = AgentState(
        task_id="test-123",
        objective="test objective",
        status="awaiting_approval",
        pending_action={"name": "run_command", "arguments": {"command": "echo hi"}}
    )
    save_task(state)

    response = client.get("/tasks/test-123")
    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_approval"

    # Test approve endpoint - just verify it runs without error
    # Mock LocalModel to return empty tool_calls so graph completes
    class MockExecutorModel:
        def __init__(self):
            self.model = "mock-qwen"
        def invoke(self, messages, tools=None):
            return {
                "content": "done",
                "tool_calls": [],
                "message": {"role": "assistant", "content": "done"}
            }

    with patch("backend.agent.executor.LocalModel", return_value=MockExecutorModel()):
        res_approve = client.post("/tasks/test-123/approve")
    assert res_approve.status_code == 200
    assert res_approve.json()["status"] in ("executing", "completed")
