from pathlib import Path
import shutil

from tools.policy import path_policy_error


WORKSPACE_ROOT = Path.cwd().resolve()


def safe_path(path: str) -> Path:
    """Resolve PC-wide paths while enforcing centralized protected-path policy."""
    candidate = Path(path)
    target = candidate if candidate.is_absolute() else WORKSPACE_ROOT / candidate
    target = target.resolve()

    error = path_policy_error(str(target))
    if error:
        raise PermissionError(error)

    return target


def read_file(path: str) -> str:
    target = safe_path(path)

    if target.is_dir():
        return f"ERROR: Path is a directory, not a file: {path}"

    try:
        raw = target.read_bytes()
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            return raw.decode("utf-16")
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig")
        return raw.decode("utf-8")
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


def create_directory(path: str) -> str:
    target = safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return f"DIRECTORY CREATED: {path}"


def copy_path(source: str, destination: str) -> str:
    src = safe_path(source)
    dst = safe_path(destination)
    if not src.exists():
        return f"ERROR: source does not exist: {source}"
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return f"COPIED: {source} -> {destination}"


def move_path(source: str, destination: str) -> str:
    src = safe_path(source)
    dst = safe_path(destination)
    if not src.exists():
        return f"ERROR: source does not exist: {source}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"MOVED: {source} -> {destination}"


def delete_path(path: str) -> str:
    target = safe_path(path)
    if target == WORKSPACE_ROOT:
        return "ERROR: refusing to delete workspace root"
    if not target.exists():
        return f"ERROR: path does not exist: {path}"
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return f"DELETED: {path}"
