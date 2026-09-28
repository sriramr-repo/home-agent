import os
from unittest.mock import patch
import pytest
from backend.tools.registry import ToolRegistry, load_generated_tool


def test_dynamic_tool_generation_and_execution():
    test_tools = {}
    registry = ToolRegistry(test_tools)
    custom_source_code = """
def dynamic_multiply(a: int, b: int) -> dict:
    return {"result": a * b}
"""
    mock_schema = {
        "type": "function",
        "function": {
            "name": "dynamic_multiply",
            "description": "Multiplies two numbers dynamically",
            "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}}
        }
    }
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(Exception, match="dynamic tool loading disabled"):
            load_generated_tool(registry, "dynamic_multiply", custom_source_code, mock_schema)

    with patch.dict(os.environ, {"MUSE_ALLOW_DYNAMIC_TOOLS": "1"}):
        load_generated_tool(registry, "dynamic_multiply", custom_source_code, mock_schema)

    assert "dynamic_multiply" in registry._tools
    tool_runner = registry.get("dynamic_multiply")
    execution_output = tool_runner(a=6, b=7)
    assert execution_output == {"result": 42}
