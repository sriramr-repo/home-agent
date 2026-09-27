from unittest.mock import Mock, patch

from backend.agent.executor import execute_task
from backend.agent.graph import build_graph
from backend.agent.model import LocalModel, ToolCall
from backend.agent.state import AgentState
from backend.agent.verifier import verify_task


class MockLocalModel(LocalModel):
    def __init__(self, responses: list[dict]):
        super().__init__(base_url="http://localhost:11434", model="test")
        self.responses = responses
        self.call_count = 0

    def invoke(self, messages, tools=None):
        if self.call_count >= len(self.responses):
            return {"content": "Done", "tool_calls": [], "message": {"role": "assistant", "content": "Done"}}
        response = self.responses[self.call_count]
        self.call_count += 1
        # Convert dict tool_calls to ToolCall objects
        calls = []
        for c in response.get("tool_calls", []):
            calls.append(ToolCall(c["name"], c["arguments"]))
        return {"content": response["content"], "tool_calls": calls, "message": response.get("message")}


def test_model_driven_tool_execution():
    """Test model-selected tool execution sequence."""
    responses = [
        {"content": "", "tool_calls": [{"name": "read_file", "arguments": {"path": "README.md"}}], "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "README.md"}}}]}},
        {"content": "File read complete", "tool_calls": [{"name": "run_command", "arguments": {"command": "ls"}}], "message": {"role": "assistant", "content": "File read complete", "tool_calls": [{"function": {"name": "run_command", "arguments": {"command": "ls"}}}]}},
        {"content": "Task complete", "tool_calls": [], "message": {"role": "assistant", "content": "Task complete"}},
    ]
    model = MockLocalModel(responses)
    
    state = AgentState(task_id="test1", objective="Read file and list directory")
    
    with patch("backend.agent.executor.LocalModel", return_value=model):
        state = execute_task(state)
        assert state.status in {"executing", "completed"}
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0]["name"] == "read_file"
        
        state = execute_task(state)
        assert len(state.tool_calls) == 2
        assert state.tool_calls[1]["name"] == "run_command"
        
        state = execute_task(state)
        assert state.status == "completed"
        assert state.result == "Task complete"
        assert len(state.tool_results) == 2


def test_model_driven_failure_recovery():
    """Test model receives failure and chooses recovery action."""
    responses = [
        {"content": "", "tool_calls": [{"name": "run_command", "arguments": {"command": "pytest --invalid"}}], "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "run_command", "arguments": {"command": "pytest --invalid"}}}]}},
        {"content": "Command failed, trying valid command", "tool_calls": [{"name": "run_command", "arguments": {"command": "ls"}}], "message": {"role": "assistant", "content": "Command failed, trying valid command", "tool_calls": [{"function": {"name": "run_command", "arguments": {"command": "ls"}}}]}},
        {"content": "Task complete", "tool_calls": [], "message": {"role": "assistant", "content": "Task complete"}},
    ]
    model = MockLocalModel(responses)
    
    state = AgentState(task_id="test2", objective="Run tests")
    
    with patch("backend.agent.executor.LocalModel", return_value=model):
        state = execute_task(state)
        assert state.status == "executing"
        assert state.tool_results[-1]["exit_code"] != 0
        
        state = execute_task(state)
        assert state.tool_results[-1]["exit_code"] == 0
        
        state = execute_task(state)
        assert state.status == "completed"


def test_tool_call_history_preserved():
    """Test Ollama tool_calls survive into next model invocation."""
    responses = [
        {"content": "", "tool_calls": [{"name": "read_file", "arguments": {"path": "test.txt"}}], "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "test.txt"}}}]}},
        {"content": "Done", "tool_calls": [], "message": {"role": "assistant", "content": "Done"}},
    ]
    model = MockLocalModel(responses)
    
    state = AgentState(task_id="test3", objective="Test history")
    
    with patch("backend.agent.executor.LocalModel", return_value=model):
        state = execute_task(state)
        assert state.messages[0]["role"] == "system"
        assert state.messages[1]["role"] == "user"
        assert state.messages[2]["role"] == "assistant"
        assert state.messages[2]["tool_calls"] == [{"function": {"name": "read_file", "arguments": {"path": "test.txt"}}}]
        assert state.messages[3]["role"] == "tool"
        assert "not found" in state.messages[3]["content"]

        state = execute_task(state)
        assert state.messages[-2]["role"] == "tool"
        assert state.messages[-1]["role"] == "assistant"
        assert state.messages[-1]["content"] == "Done"


def test_verifier_rejects_failed_evidence():
    """Test verifier rejects failed tool results as evidence."""
    state = AgentState(
        task_id="test4",
        objective="Test",
        result="Done",
        tool_results=[
            {"ok": False, "error": "failed"},
            {"exit_code": 1, "stdout": "", "stderr": "error"},
        ],
    )
    
    result = verify_task(state)
    assert result.status == "failed"
    assert "Latest validation evidence failed" in result.error


def test_verifier_accepts_successful_evidence():
    """Test verifier accepts successful tool results."""
    state = AgentState(
        task_id="test5",
        objective="Test",
        result="Done",
        tool_results=[
            {"ok": True, "changed": True},
            {"exit_code": 0, "stdout": "success"},
        ],
        files_changed=["test.txt"],
    )
    
    result = verify_task(state)
    assert result.status == "completed"
    assert result.error is None


def test_iteration_limit_pass_on_fifth_round():
    """Test 1 — PASS on fifth round with max_agent_iterations=5."""
    responses = [
        {"content": "", "tool_calls": ["run_command"], "message": {"role": "assistant", "content": ""}} # r1: fail pytest
    ]
    # We test via build_graph with mocked model returning failing then succeeding pytest
    call_seq = iter([
        {"content": "", "tool_calls": [ToolCall("run_command", {"command": "pytest --invalid"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "a.py"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "b.py"})]},
        {"content": "", "tool_calls": [ToolCall("edit_file", {"path": "a.py", "old_content": "x", "new_content": "y"})]},
        {"content": "", "tool_calls": [ToolCall("run_command", {"command": "pytest"})]},
    ])
    class FifthRoundModel:
        def invoke(self, messages, tools=None):
            return next(call_seq)

    state = AgentState(
        task_id="test_iter_pass",
        objective="Fix and test",
        max_agent_iterations=5,
    )
    planner_model = Mock()
    planner_model.invoke.return_value = {"content": '{"steps": ["a"]}', "tool_calls": [], "message": {"role": "assistant", "content": ""}}
    with patch("backend.agent.executor.LocalModel", return_value=FifthRoundModel()), \
         patch("backend.agent.planner.LocalModel", return_value=planner_model), \
         patch("backend.agent.executor.REGISTRY", new={"run_command": Mock(side_effect=[{"exit_code": 1, "stdout": "fail", "command": "pytest --invalid"}, {"exit_code": 0, "stdout": "1 passed", "command": "pytest"}]), "edit_file": Mock(return_value={"ok": True, "changed": True}), "read_file": Mock(return_value={"content": "content", "error": None}), "list_files": Mock(return_value={"files": []}), "search_code": Mock(return_value={}), "write_file": Mock(return_value={"ok": True}), "git_status": Mock(return_value={}), "git_diff": Mock(return_value={})}), \
         patch("backend.tools.filesystem.Workspace.read_file", return_value={"content": "content", "error": None}):
        final = AgentState.model_validate(build_graph().invoke(state))
    assert len(final.model_invocations) == 5
    assert final.status == "completed"
    assert final.verification_results.get("passed") is True


def test_iteration_limit_fail_on_fifth_round():
    """Test 2 — FAIL on fifth round with max_agent_iterations=5 (pytest fails)."""
    call_seq = iter([
        {"content": "", "tool_calls": [ToolCall("run_command", {"command": "pytest"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "a.py"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "b.py"})]},
        {"content": "", "tool_calls": [ToolCall("edit_file", {"path": "a.py", "old_content": "x", "new_content": "y"})]},
        {"content": "", "tool_calls": [ToolCall("run_command", {"command": "pytest"})]},
    ])
    class FailModel:
        def invoke(self, messages, tools=None):
            return next(call_seq)

    state = AgentState(
        task_id="test_iter_fail",
        objective="Fix and test fail",
        max_agent_iterations=5,
    )
    planner_model = Mock()
    planner_model.invoke.return_value = {"content": '{"steps": ["a"]}', "tool_calls": [], "message": {"role": "assistant", "content": ""}}
    with patch("backend.agent.executor.LocalModel", return_value=FailModel()), \
         patch("backend.agent.planner.LocalModel", return_value=planner_model), \
         patch("backend.agent.executor.REGISTRY", new={"run_command": Mock(return_value={"exit_code": 1, "stdout": "fail", "command": "pytest"}), "edit_file": Mock(return_value={"ok": True, "changed": True}), "read_file": Mock(return_value={"content": "content", "error": None}), "list_files": Mock(return_value={"files": []}), "search_code": Mock(return_value={}), "write_file": Mock(return_value={"ok": True}), "git_status": Mock(return_value={}), "git_diff": Mock(return_value={})}), \
         patch("backend.tools.filesystem.Workspace.read_file", return_value={"content": "content", "error": None}):
        final = AgentState.model_validate(build_graph().invoke(state))
    assert len(final.model_invocations) == 5
    assert final.status == "failed"
    assert "max agent iterations exceeded" in final.error


def test_successful_non_verification_tool_on_fifth_round():
    """Test 3 — Successful non-verification tool (read_file) on round 5 does not trigger false completion."""
    call_seq = iter([
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "1.py"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "2.py"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "3.py"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "4.py"})]},
        {"content": "", "tool_calls": [ToolCall("read_file", {"path": "5.py"})]},
    ])
    class ReadModel:
        def invoke(self, messages, tools=None):
            return next(call_seq)

    state = AgentState(
        task_id="test_iter_read",
        objective="Read files",
        max_agent_iterations=5,
    )
    planner_model = Mock()
    planner_model.invoke.return_value = {"content": '{"steps": ["a"]}', "tool_calls": [], "message": {"role": "assistant", "content": ""}}
    with patch("backend.agent.executor.LocalModel", return_value=ReadModel()), \
         patch("backend.agent.planner.LocalModel", return_value=planner_model), \
         patch("backend.agent.executor.REGISTRY", new={"read_file": Mock(return_value={"content": "ok", "error": None}), "list_files": Mock(return_value={"files": []}), "search_code": Mock(return_value={}), "run_command": Mock(return_value={"exit_code": 0}), "edit_file": Mock(return_value={"ok": True}), "write_file": Mock(return_value={"ok": True}), "git_status": Mock(return_value={}), "git_diff": Mock(return_value={})}), \
         patch("backend.tools.filesystem.Workspace.read_file", return_value={"content": "ok", "error": None}):
        final = AgentState.model_validate(build_graph().invoke(state))
    assert len(final.model_invocations) == 5
    assert final.status == "failed"
    assert "max agent iterations exceeded" in final.error


def test_provider_factory():
    """Test model provider factory and adapter configurations."""
    from backend.agent.model import get_model_provider, LocalModel, NineRouterModel, ModelProviderError
    with patch.dict("os.environ", {"LLM_PROVIDER": "ollama"}):
        p = get_model_provider()
        assert isinstance(p, LocalModel)
    with patch.dict("os.environ", {"LLM_PROVIDER": "9router", "LLM_BASE_URL": "https://example.com", "LLM_MODEL": "gpt-4o"}):
        p = get_model_provider()
        assert isinstance(p, NineRouterModel)
    with patch.dict("os.environ", {"LLM_PROVIDER": "invalid"}):
        import pytest
        with pytest.raises(ModelProviderError):
            get_model_provider()