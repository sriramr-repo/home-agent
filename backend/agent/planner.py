from __future__ import annotations

import json
from .model import get_model_provider

LocalModel = get_model_provider
from .state import AgentState
from ..tools.filesystem import Workspace


def plan_task(state: AgentState) -> AgentState:
    if state.status == "failed":
        return state
    state.status = "planning"
    ws = Workspace(state.repository_path)
    files_info = ws.list_files(".")
    file_list = files_info.get("files", [])

    if "FAIL_TOOL" in state.objective:
        state.plan = ["Inspect repository", "Execute failing tool", "Observe error", "Debug", "Verify"]
        state.current_step = 0
        state.current_step_name = "planning"
        return state

    model = LocalModel()
    prompt = (
        "You are the Muse agent planner. Given the user objective and repository file list, "
        "return a JSON object with keys 'goal', 'steps' (list of strings), and 'validation' (list of strings).\n"
        f"Objective: {state.objective}\n"
        f"Repository files: {file_list[:100]}\n"
        "Respond ONLY with valid JSON."
    )
    try:
        res = model.invoke([{"role": "user", "content": prompt}])
        content = res["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content.rsplit("\n", 1)[0]
        parsed = json.loads(content)
        state.plan = parsed.get("steps", ["Inspect", "Implement", "Verify"])
    except Exception:
        state.plan = ["Inspect repository", "Implement objective", "Verify results"]

    state.current_step = 0
    state.current_step_name = "planning"
    return state