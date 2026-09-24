import subprocess

def run(command: str) -> str:
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True
    )

    output = result.stdout + result.stderr
    return f"EXIT CODE: {result.returncode}\n{output}"
