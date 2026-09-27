from .terminal import run_command

def git_status(workspace=None):
    return run_command("git status --short", workspace=workspace)

def git_diff(workspace=None):
    return run_command("git diff", workspace=workspace)