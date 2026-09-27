from typing import Any


def mock_research(objective: str) -> dict[str, Any]:
    if "FAIL_TOOL" in objective:
        raise RuntimeError("Mock research tool failure requested")
    return {
        "tool": "mock_research",
        "objective": objective,
        "summary": "Mock research completed successfully.",
        "sources": [],
        "mock": True,
    }