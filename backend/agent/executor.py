from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from ..tools.editor import edit_file, write_file
from ..tools.filesystem import Workspace
from ..tools.git import git_diff, git_status
from ..tools.registry import TOOL_SCHEMAS, ToolRegistry, enforce_sandbox_acl
from ..tools.terminal import run_command
from .model import get_model_provider, ModelProviderError, _TRUNCATED

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

logger = logging.getLogger("muse.agent")

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
            enforce_sandbox_acl(c_args, st.user_id, st.project_id)
            result = REGISTRY.get(c_name)(**c_args, workspace=workspace)
        except PermissionError as exc:
            logger.error(
                "sandbox ACL denied task_id=%s user_id=%s project_id=%s tool=%s args=%s",
                st.task_id, st.user_id, st.project_id, c_name, c_args,
            )
            result = {"ok": False, "error": str(exc)}
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
            logger.info("approval consumed task_id=%s approved=False tool=%s", state.task_id, p_name)
            state.messages.append({"role": "tool", "tool_name": p_name, "content": denied})
            state.tool_results.append({"ok": False, "error": denied})
            state.observations.append(denied)
            return state
        if state.user_approval is True:
            state.user_approval = None
            state.status = "executing"
            logger.info(
                "approval consumed task_id=%s approved=True tool=%s",
                state.task_id,
                _call_parts(pending)[0],
            )
            return _run_calls(state, [pending])
        state.status = "awaiting_approval"
        state.pending_action = pending
        return state

    state.status = "executing"
    state.current_step += 1
    state.iteration_count += 1
    logger.info(
        "execution start task_id=%s iteration=%s elapsed_total=%.3fs",
        state.task_id,
        state.iteration_count,
        state.total_execution_time,
    )

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
        elapsed = time.monotonic() - started
        state.total_execution_time += elapsed
        state.compacted_turns_count = sum(1 for m in state.messages if m.get("content") == _TRUNCATED)
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
        logger.error(
            "model provider failed task_id=%s elapsed=%.3fs error=%s",
            state.task_id,
            time.monotonic() - started,
            exc,
            exc_info=True,
        )
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
        logger.info(
            "suspended for approval task_id=%s tool=%s elapsed_total=%.3fs",
            state.task_id,
            high_risk["name"],
            state.total_execution_time,
        )
        return state

    # ponytail: Keep user_approval flag intact for multi-turn runs until upgraded.
    return _run_calls(state, norm_calls)
