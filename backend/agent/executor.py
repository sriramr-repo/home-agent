from __future__ import annotations

import json
import os
import time
from typing import Any

from ..tools.editor import edit_file, write_file
from ..tools.filesystem import Workspace
from ..tools.git import git_diff, git_status
from ..tools.registry import TOOL_SCHEMAS, ToolRegistry
from ..tools.terminal import run_command
from .model import get_model_provider, ModelProviderError

LocalModel = get_model_provider
from .state import AgentState
from .verifier import is_pytest_verification, record_verification

_TOOLS = {
    "list_files": lambda path=".", workspace=None: (workspace or Workspace()).list_files(path),
    "read_file": lambda path, workspace=None: (workspace or Workspace()).read_file(path),
    "search_code": lambda query, workspace=None: (workspace or Workspace()).search_code(query),
    "write_file": write_file,
    "edit_file": edit_file,
    "run_command": run_command,
    "git_status": git_status,
    "git_diff": git_diff,
}

REGISTRY = ToolRegistry(_TOOLS)
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "20"))
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "50"))
_HIGH_RISK_TOOLS = {"run_command", "write_file", "edit_file"}


def _call_parts(call: Any) -> tuple[str, dict[str, Any]]:
    if hasattr(call, "name"):
        return call.name, call.arguments
    return call.get("name"), call.get("arguments", {})


def _run_calls(st: AgentState, clls: list[Any]) -> AgentState:
    workspace = Workspace(st.repository_path)
    iteration_limit = st.max_agent_iterations or MAX_AGENT_ITERATIONS
    for call in clls:
        c_name, c_args = _call_parts(call)
        record = {"name": c_name, "arguments": c_args}
        st.tool_calls.append(record)
        if len(st.tool_calls) > MAX_TOOL_CALLS:
            st.status, st.error = "failed", "max tool calls exceeded"
            return st
        try:
            result = REGISTRY.get(c_name)(**c_args, workspace=workspace)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        st.tool_results.append(result)
        st.messages.append({"role": "tool", "tool_name": c_name, "content": json.dumps(result)})
        st.observations.append(json.dumps(result))
        if c_name in {"write_file", "edit_file"} and (result.get("changed") or result.get("error") is None):
            st.files_changed.append(c_args.get("path", ""))
        if c_name in {"read_file", "list_files"} and result.get("error") is None:
            st.files_changed.append(c_args.get("path", ""))
        if c_name == "run_command":
            st.commands_executed.append(c_args.get("command", ""))
        if is_pytest_verification(result):
            record_verification(st, result)
            if result["exit_code"] == 0:
                st.status = "completed"
            elif st.iteration_count >= iteration_limit:
                st.status, st.error = "failed", "max agent iterations exceeded"
                if st.error not in st.errors:
                    st.errors.append(st.error)
    return st


def execute_task(state: AgentState) -> AgentState:
    if state.status in {"completed", "failed"}:
        return state

    if state.pending_action:
        pending = state.pending_action
        state.pending_action = None
        if state.user_approval is False:
            state.user_approval = None
            state.status = "executing"
            denied = "Tool execution explicitly denied by user."
            p_name, _ = _call_parts(pending)
            state.messages.append({"role": "tool", "tool_name": p_name, "content": denied})
            state.tool_results.append({"ok": False, "error": denied})
            state.observations.append(denied)
            return state
        if state.user_approval is True:
            state.user_approval = None
            state.status = "executing"
            return _run_calls(state, [pending])
        state.status = "awaiting_approval"
        state.pending_action = pending
        return state

    state.status = "executing"
    state.current_step += 1
    state.iteration_count += 1

    if not state.messages:
        state.messages.extend([
            {"role": "system", "content": "Use tools to complete the objective. Return no tool calls only when finished."},
            {"role": "user", "content": state.objective},
        ])

    iteration_limit = state.max_agent_iterations or MAX_AGENT_ITERATIONS
    if state.iteration_count > iteration_limit:
        state.status = "failed"
        state.error = "max agent iterations exceeded"
        return state

    model = None
    started = time.monotonic()
    try:
        model = LocalModel()
        response = model.invoke(state.messages, TOOL_SCHEMAS)
    except ModelProviderError as exc:
        state.model_invocations.append({
            "invocation": len(state.model_invocations) + 1,
            "model": getattr(model, "model", "mock"),
            "elapsed": time.monotonic() - started,
            "tool_calls": False,
            "tool_names": [],
            "succeeded": False,
            "error": str(exc),
        })
        state.status = "failed"
        state.error = str(exc)
        return state

    calls = response.get("tool_calls", [])
    state.model_invocations.append({
        "invocation": len(state.model_invocations) + 1,
        "model": getattr(model, "model", "mock"),
        "elapsed": time.monotonic() - started,
        "tool_calls": bool(calls),
        "tool_names": [c.name if hasattr(c, "name") else c.get("name") for c in calls],
        "succeeded": True,
    })
    content = response.get("content", "")
    assistant_msg = dict(response.get("message", {"role": "assistant", "content": content}))
    assistant_msg["role"] = "assistant"
    assistant_msg.setdefault("content", content)
    state.messages.append(assistant_msg)

    if not calls:
        state.result = content
        state.status = "completed"
        return state

    norm_calls = [{"name": n, "arguments": a} for n, a in map(_call_parts, calls)]
    high_risk = next((c for c in norm_calls if c["name"] in _HIGH_RISK_TOOLS), None)
    if high_risk and state.user_approval is not True:
        state.pending_action = high_risk
        state.status = "awaiting_approval"
        return state

    # ponytail: Keep user_approval flag intact for multi-turn runs until upgraded.
    return _run_calls(state, norm_calls)
