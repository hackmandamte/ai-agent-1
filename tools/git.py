import subprocess

from .shell import run
from .files import WORKSPACE_ROOT


def git_status() -> str:
    return run("git status --short")


def git_diff() -> str:
    return run("git diff")


def git_log() -> str:
    return run("git log --oneline -10")


def git_commit(message: str) -> str:
    add = subprocess.run(
        ["git", "add", "-A"],
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
    )

    if add.returncode != 0:
        return f"EXIT CODE: {add.returncode}\n{add.stdout}{add.stderr}"

    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
    )

    output = commit.stdout + commit.stderr
    return f"EXIT CODE: {commit.returncode}\n{output}"
