from pathlib import Path
import os

_SECRET_NAMES = {".env", ".env.local", ".env.production", "credentials", "id_rsa", ".git"}

class Workspace:
    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()

    def path(self, value: str) -> Path:
        p = (self.root / value).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError("path escapes workspace")
        if p.name in _SECRET_NAMES or p.suffix in {".pem", ".key"}:
            raise PermissionError("secret file access denied")
        return p

    def list_files(self, path=".") -> dict:
        p = self.path(path)
        files = []
        for x in p.rglob("*"):
            if x.is_file() and not any(part in _SECRET_NAMES for part in x.parts):
                try:
                    files.append(str(x.relative_to(self.root)))
                except ValueError:
                    pass
        return {"path": path, "files": sorted(files)}

    def read_file(self, path) -> dict:
        p = self.path(path)
        try:
            return {"path": path, "content": p.read_text(encoding="utf-8"), "error": None}
        except UnicodeDecodeError:
            return {"path": path, "content": None, "error": "binary file"}
        except FileNotFoundError:
            return {"path": path, "content": None, "error": "not found"}

    def search_code(self, query: str) -> dict:
        matches = []
        for item in self.root.rglob("*"):
            if item.is_file() and not any(part in _SECRET_NAMES for part in item.parts):
                try:
                    for n, line in enumerate(item.read_text(encoding="utf-8").splitlines(), 1):
                        if query in line:
                            matches.append({"path": str(item.relative_to(self.root)), "line": n, "text": line})
                except (UnicodeDecodeError, OSError):
                    pass
        return {"query": query, "matches": matches}

def list_files(path=".", workspace=None):
    return (workspace or Workspace()).list_files(path)
def read_file(path, workspace=None):
    return (workspace or Workspace()).read_file(path)
def search_code(query, workspace=None):
    return (workspace or Workspace()).search_code(query)