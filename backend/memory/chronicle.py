from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..agent.state import AgentState
from ..tools.registry import tenant_root

logger = logging.getLogger("muse.agent")


MUTATING_TOOLS = {"run_command", "write_file", "edit_file"}


def log_event(state: AgentState, node_name: str, mutation_phase: str = "settled") -> None:
    """Append an execution turn snapshot as JSONL to the tenant chronicle.

    ``mutation_phase`` is the taint marker: "pending_mutation" is written before a
    worker fires a mutating tool, and the next settled event supersedes it. A
    chronicle whose final record is still "pending_mutation" means the process
    died mid-write, so the workspace is suspect on the next boot.
    """
    try:
        root = tenant_root(state.user_id, state.project_id)
        root.mkdir(parents=True, exist_ok=True)
        chronicle_file = root / "chronicle.jsonl"
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": state.user_id,
            "project_id": state.project_id,
            "task_id": state.task_id,
            "node_name": node_name,
            "mutation_phase": mutation_phase,
            "status": state.status,
            "current_step": state.current_step,
            "objective": state.objective,
            "messages": state.messages,
            "tool_calls": state.tool_calls,
            "tool_results": state.tool_results,
            "total_execution_time": state.total_execution_time,
            "compacted_turns_count": state.compacted_turns_count,
            "workspace_taint_status": state.workspace_taint_status,
        }
        with chronicle_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            # Durability matters here: a buffered pending marker that never reaches
            # disk defeats the entire guard.
            f.flush()
    except Exception:
        # ponytail: recording must never take down a live run. Promote to a
        # counter/alert once chronicle data is load-bearing for billing or audit.
        logger.exception("chronicle write failed task_id=%s node=%s", state.task_id, node_name)


def log_pending_mutation(state: AgentState, node_name: str, tool_names: list[str]) -> None:
    """Mark the workspace as mid-mutation before a mutating tool executes."""
    if not any(name in MUTATING_TOOLS for name in tool_names):
        return
    log_event(state, node_name, mutation_phase="pending_mutation")


def rehydrate_and_replay_task(user_id: str, project_id: str) -> AgentState | None:
    """Replay chronicle.jsonl to rebuild the latest AgentState snapshot.

    If the chronicle's last usable record carries
    ``mutation_phase == "pending_mutation"``, the process crashed while a
    mutating tool was inflight. The rehydrated state is marked
    ``workspace_taint_status = "interrupted_execution"`` so the caller can
    trigger cleanup or quarantine.
    """
    root = tenant_root(user_id, project_id)
    chronicle_file = root / "chronicle.jsonl"
    if not chronicle_file.exists():
        return None

    last_state: dict[str, Any] | None = None
    corrupted = 0
    with chronicle_file.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                last_state = json.loads(line)
            except json.JSONDecodeError as exc:
                corrupted += 1
                logger.error(
                    "chronicle line corrupt user_id=%s project_id=%s task_id=%s line=%d error=%s",
                    user_id,
                    project_id,
                    (last_state or {}).get("task_id", "unknown"),
                    lineno,
                    exc,
                )

    if last_state is None:
        if corrupted:
            raise ValueError(
                f"chronicle for {user_id}/{project_id} holds no replayable event ({corrupted} corrupt lines)"
            )
        return None

    taint = None
    phase = last_state.get("mutation_phase")
    if phase == "pending_mutation":
        taint = "interrupted_execution"
        logger.warning(
            "chronicle taint detected task_id=%s user_id=%s project_id=%s",
            last_state.get("task_id", "unknown"),
            user_id,
            project_id,
        )

    state = AgentState.model_validate({**last_state, "user_id": user_id, "project_id": project_id})
    if taint:
        state.workspace_taint_status = taint
    if corrupted and "corrupted_log" not in state.errors:
        state.errors.append("corrupted_log")
        logger.error(
            "chronicle replay incomplete task_id=%s corrupt_lines=%d", state.task_id, corrupted
        )
    return state
