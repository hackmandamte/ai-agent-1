from pathlib import Path

def read_file(path: str) -> str:
    return Path(path).read_text()

def write_file(path: str, content: str) -> str:
    Path(path).write_text(content)
    return f"Written: {path}"

def list_files(path: str = ".") -> str:
    return "\n".join(str(p) for p in Path(path).iterdir())
