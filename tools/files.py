from pathlib import Path

WORKSPACE_ROOT = Path.cwd().resolve()


def safe_path(path: str) -> Path:
    target = (WORKSPACE_ROOT / path).resolve()

    if target != WORKSPACE_ROOT and WORKSPACE_ROOT not in target.parents:
        raise ValueError(f"Path outside workspace: {path}")

    return target


def read_file(path: str) -> str:
    return safe_path(path).read_text()


def write_file(path: str, content: str) -> str:
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Written: {path}"


def list_files(path: str = ".") -> str:
    return "\n".join(
        str(p.relative_to(WORKSPACE_ROOT))
        for p in safe_path(path).iterdir()
    )
