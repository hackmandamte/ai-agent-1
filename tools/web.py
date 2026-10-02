"""Read public web pages through the host PowerShell network stack."""
import subprocess

MAX_OUTPUT = 20000
TIMEOUT_SECONDS = 20


def web_fetch(url: str) -> str:
    """Fetch a public HTTP(S) URL as text without exposing shell execution."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return "ERROR: URL must start with http:// or https://"

    script = (
        "$ProgressPreference='SilentlyContinue'; "
        "$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec "
        + str(TIMEOUT_SECONDS)
        + " -Uri '"
        + url.replace("'", "''")
        + "'; "
        "$r.StatusCode; $r.Content"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS + 5,
        check=False,
    )
    if result.returncode != 0:
        return "ERROR: web fetch failed: " + (result.stderr.strip() or result.stdout.strip())

    output = result.stdout
    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + "\n[truncated]"
    return output


def web_fetch_definition():
    return {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a public HTTP or HTTPS URL and return its text. Read-only internet access.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    }
