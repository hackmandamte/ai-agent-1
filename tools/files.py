from pathlib import Path


WORKSPACE_ROOT = Path.cwd().resolve()


def safe_path(path: str) -> Path:
    """Resolve a workspace-relative or in-workspace absolute path safely."""
    workspace_root = WORKSPACE_ROOT.resolve()
    candidate = Path(path)

    # Path joining already handles absolute paths, but making the two cases
    # explicit prevents platform-specific pathlib behavior from weakening the
    # workspace boundary.
    if candidate.is_absolute():
        target = candidate
    else:
        target = workspace_root / candidate

    target = target.resolve()

    if target != workspace_root and workspace_root not in target.parents:
        raise ValueError(f"Path outside workspace: {path}")

    return target


def read_file(path: str) -> str:
    target = safe_path(path)

    if target.is_dir():
        return f"ERROR: Path is a directory, not a file: {path}"

    try:
        return target.read_text(encoding="utf-8")
    except IsADirectoryError:
        # A directory can be replaced between the check and the read.
        return f"ERROR: Path is a directory, not a file: {path}"


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
