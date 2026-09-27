from .filesystem import Workspace


def write_file(path: str, content: str, workspace: Workspace | None = None, *, overwrite: bool = False) -> dict:
    ws = workspace or Workspace()
    target = ws.path(path)
    if target.exists() and not overwrite:
        return {"ok": False, "path": path, "changed": False, "error": "file already exists"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "changed": True, "error": None}


def edit_file(path: str, old_content: str, new_content: str, workspace: Workspace | None = None) -> dict:
    ws = workspace or Workspace()
    target = ws.path(path)
    try:
        current = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"ok": False, "path": path, "changed": False, "error": "not found"}
    except UnicodeDecodeError:
        return {"ok": False, "path": path, "changed": False, "error": "binary file"}
    if old_content not in current:
        return {"ok": False, "path": path, "changed": False, "error": "expected content not found"}
    target.write_text(current.replace(old_content, new_content, 1), encoding="utf-8")
    return {"ok": True, "path": path, "changed": True, "error": None}
