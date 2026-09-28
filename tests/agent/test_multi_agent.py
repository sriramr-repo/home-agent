from unittest.mock import patch
from backend.agent.model import ToolCall
from backend.agent.runtime import run_agent
from backend.agent.state import AgentState


def test_multi_agent_sentinel_gate():
    calls = iter([
        {
            "content": "",
            "tool_calls": [ToolCall("run_command", {"command": "rm -rf /"})],
            "message": {"role": "assistant", "content": ""},
        }
    ])

    class MockMultiModel:
        def invoke(self, messages, tools=None):
            return next(calls)

    planner_model = MockMultiModel()
    planner_model.invoke = lambda m, t=None: {"content": '{"steps": ["Run command"]}', "tool_calls": [], "message": {"role": "assistant", "content": ""}}

    with patch("backend.agent.planner.LocalModel", return_value=planner_model), \
         patch("backend.agent.executor.LocalModel", return_value=MockMultiModel()):
        result = run_agent("Dangerous task", use_multi_agent=True)
        assert result.status == "awaiting_approval"
        assert result.pending_action is not None
        assert result.pending_action["name"] == "run_command"
