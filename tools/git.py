from .shell import run

def git_status() -> str:
    return run("git status --short")

def git_diff() -> str:
    return run("git diff")

def git_log() -> str:
    return run("git log --oneline -10")

def git_commit(message: str) -> str:
    return run(f'git add -A && git commit -m "{message}"')
