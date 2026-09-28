import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

Tool = Callable[..., dict[str, Any]]

SANDBOX_ROOT = Path(os.getenv("SANDBOX_ROOT", "/tmp/sandbox_workspace"))
_ACL_DENIED = "Sandbox ACL violation: Access to unauthorized directory denied."
_PATH_ARGS = ("path", "cwd")


def tenant_root(user_id: str = "local", project_id: str = "default") -> Path:
    """Absolute sandbox dir for one tenant: /tmp/sandbox_workspace/{user}/{project}."""
    for part in (user_id, project_id):
        if not part or "/" in part or part in {".", ".."}:
            raise PermissionError(_ACL_DENIED)
    return (SANDBOX_ROOT / user_id / project_id).resolve()


def enforce_sandbox_acl(
    arguments: dict[str, Any],
    user_id: str = "local",
    project_id: str = "default",
) -> None:
    """Reject tool args whose path escapes the caller\'s tenant sandbox.

    ponytail: guards declared path arguments only. A command string that embeds
    its own paths (run_command) is still bounded by terminal.py allowlisting;
    parse argv here if that allowlist is ever relaxed.
    """
    root = tenant_root(user_id, project_id)
    for key in _PATH_ARGS:
        value = arguments.get(key)
        if not isinstance(value, str):
            continue
        target = Path(value)
        resolved = (target if target.is_absolute() else root / target).resolve()
        if resolved != root and root not in resolved.parents:
            raise PermissionError(_ACL_DENIED)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List workspace files",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a workspace text file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search workspace text",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a workspace file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one exact workspace text span",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_content": {"type": "string"},
                    "new_content": {"type": "string"}
                },
                "required": ["path", "old_content", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run an allowed development command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]


GENERATED_TOOLS_PATH = Path(__file__).with_name("generated_tools.py")


class ToolRegistry:
    def __init__(self, tools: dict[str, Tool]) -> None:
        self._tools = tools

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def register_dynamic_tool(self, name: str, func_callable: Tool, schema: dict[str, Any]) -> None:
        """Inject a tool into dispatch and advertise its schema to the model."""
        if not name or not callable(func_callable):
            raise ValueError("dynamic tool needs a name and a callable")
        self._tools[name] = func_callable
        for i, existing in enumerate(TOOL_SCHEMAS):
            if existing.get("function", {}).get("name") == name:
                TOOL_SCHEMAS[i] = schema
                break
        else:
            TOOL_SCHEMAS.append(schema)


def load_generated_tool(
    registry: ToolRegistry, name: str, source: str, schema: dict[str, Any]
) -> Tool:
    """Persist agent-authored source, import it, and register the callable.

    SECURITY: source runs with full backend-process privileges. It is NOT bounded
    by enforce_sandbox_acl, which only inspects declared path arguments of already
    registered tools. Anything exec'd here can reach the filesystem and network
    directly. Gate every call behind the Sentinel approval path and keep
    MUSE_ALLOW_DYNAMIC_TOOLS unset in production.

    ponytail: single shared generated_tools.py, appended per call. Move to one
    module per tool (and a subprocess runner) when more than a handful accumulate.
    """
    if os.getenv("MUSE_ALLOW_DYNAMIC_TOOLS") != "1":
        raise PermissionError("dynamic tool loading disabled; set MUSE_ALLOW_DYNAMIC_TOOLS=1")
    if not name.isidentifier():
        raise ValueError(f"invalid tool name: {name!r}")

    header = "" if GENERATED_TOOLS_PATH.exists() else "# Agent-generated tools. Do not edit by hand.\n"
    with GENERATED_TOOLS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{header}\n{source.rstrip()}\n")

    spec = importlib.util.spec_from_file_location("backend.tools.generated_tools", GENERATED_TOOLS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load generated_tools.py")
    module = importlib.util.module_from_spec(spec)
    # Bind before exec so the module survives reload without leaking stale copies.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    func = getattr(module, name, None)
    if not callable(func):
        raise AttributeError(f"generated source defines no callable named {name!r}")
    registry.register_dynamic_tool(name, func, schema)
    return func
