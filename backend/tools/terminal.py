import os, shlex, subprocess
from .filesystem import Workspace

DEFAULT_ALLOWED = {"npm", "npx", "node", "python", "python3", "pytest", "pip", "git", "ls", "pwd", "cat", "mkdir", "touch", "cp", "mv", "rm"}

def run_command(command: str, cwd: str = ".", workspace=None, timeout: int = 30, allowed=None) -> dict:
    ws = workspace or Workspace()
    directory = ws.path(cwd)
    argv = shlex.split(command)
    if not argv or argv[0] not in (allowed or DEFAULT_ALLOWED):
        return {"command": command, "exit_code": -1, "stdout": "", "stderr": "command not allowed", "timed_out": False}
    try:
        p = subprocess.run(
            argv,
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"}},
        )
        return {"command": command, "exit_code": p.returncode, "stdout": p.stdout[-20000:], "stderr": p.stderr[-20000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        return {"command": command, "exit_code": -1, "stdout": (e.stdout or "")[-20000:] if isinstance(e.stdout, str) else "", "stderr": "timeout", "timed_out": True}