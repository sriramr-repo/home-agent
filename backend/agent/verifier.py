from .state import AgentState


def _successful(result: dict) -> bool:
    if result.get("ok") is False or result.get("success") is False:
        return False
    if result.get("timed_out") is True or result.get("exception"):
        return False
    if "exit_code" in result:
        return result["exit_code"] == 0
    if "error" in result:
        return result["error"] is None
    return bool(result.get("ok", result.get("success", True)))


def is_pytest_verification(result: dict) -> bool:
    return (
        isinstance(result, dict)
        and isinstance(result.get("command"), str)
        and result["command"].strip().split(maxsplit=1)[0] == "pytest"
        and "exit_code" in result
    )


def record_verification(state: AgentState, result: dict) -> None:
    state.verification_results = {
        "tool": "pytest",
        "command": result["command"],
        "exit_code": result["exit_code"],
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "passed": result["exit_code"] == 0,
    }


def verify_task(state: AgentState) -> AgentState:
    if state.status in {"failed", "completed"}:
        return state
    if not state.result:
        state.error = "No final model response"
    elif not state.tool_results and not state.files_changed and not state.commands_executed:
        state.error = "No evidence of work performed"
    elif not _successful(state.tool_results[-1]):
        state.error = "Latest validation evidence failed"
    else:
        state.status = "completed"
        return state

    state.status = "failed"
    if state.error not in state.errors:
        state.errors.append(state.error)
    return state
