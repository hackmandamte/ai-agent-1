"""Platform-independent runtime detection for the agent and its tools."""

import os
import platform
import sys
from pathlib import Path


# These variables are set by PowerShell. Unlike COMSPEC, which normally
# points at cmd.exe even when PowerShell is the interactive shell, they are
# useful PowerShell indicators when SHELL is not available on Windows.
_POWERSHELL_ENVIRONMENT_MARKERS = (
    "PSModulePath",
    "PSExecutionPolicyPreference",
    "PSHOME",
    "PSEdition",
    "PSNativeCommandArgumentPassing",
    "POWERSHELL_DISTRIBUTION_CHANNEL",
)


def _environment_value(name: str):
    """Return an environment value, accepting different casings on any OS."""
    value = os.environ.get(name)
    if value is not None:
        return value

    # os.environ is case-insensitive on Windows, but a plain dictionary (as
    # used by some callers and tests) is not. Keep this lookup platform-
    # independent so simulated environments are handled consistently too.
    normalized_name = name.casefold()
    for key, value in os.environ.items():
        if key.casefold() == normalized_name:
            return value
    return None


def _shell_basename(value: str) -> str:
    """Extract a normalized executable name from a shell environment value."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()

    if not value:
        return ""

    # Parsing both separators explicitly avoids making assumptions about the
    # host OS when a Windows path is inspected on another platform (and vice
    # versa).
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    if name.casefold().endswith(".exe"):
        name = name[:-4]
    return name.casefold()


def _is_powershell_name(name: str) -> bool:
    return name in {"powershell", "powershell_ise", "pwsh"} or name.startswith(
        "pwsh-"
    )


def _is_command_prompt_name(name: str) -> bool:
    return name in {"cmd", "command", "commandprompt"}


def _shell_name(value: str):
    """Return a friendly shell name for a value from SHELL or COMSPEC."""
    name = _shell_basename(value)
    if not name:
        return None
    if _is_powershell_name(name):
        return "PowerShell"
    if _is_command_prompt_name(name):
        return "Command Prompt"
    return name


def _detect_shell(system: str) -> str:
    """Detect the current shell using portable environment signals."""
    is_windows = system.casefold() == "windows"
    shell_value = _environment_value("SHELL")
    shell_name = _shell_name(shell_value) if shell_value else None

    # An explicit PowerShell or Command Prompt selection is stronger than
    # defaults inherited from the parent process.
    if shell_name in {"PowerShell", "Command Prompt"}:
        return shell_name

    if is_windows:
        if any(_environment_value(name) for name in _POWERSHELL_ENVIRONMENT_MARKERS):
            return "PowerShell"

        # COMSPEC conventionally points to cmd.exe. Do not treat its mere
        # presence as evidence of PowerShell; identify cmd.exe by its name.
        compspec = _environment_value("COMSPEC")
        if compspec:
            compspec_name = _shell_name(compspec)
            if compspec_name in {"PowerShell", "Command Prompt"}:
                return compspec_name

        # A generic SHELL value can represent Git Bash or another shell used
        # on Windows, so retain it when there is no Windows-specific signal.
        if shell_name:
            return shell_name
        return "Windows"

    # SHELL is the standard source on Unix-like systems. The environment
    # markers below provide a useful fallback for non-login shells as well.
    if shell_name:
        return shell_name

    if _environment_value("BASH_VERSION"):
        return "bash"
    if _environment_value("ZSH_VERSION"):
        return "zsh"
    if _environment_value("FISH_VERSION"):
        return "fish"

    return "unknown"


def _operating_system_name(system: str) -> str:
    normalized_system = system.casefold()
    if normalized_system == "darwin":
        return "macOS"
    if normalized_system == "windows":
        return "Windows"
    if normalized_system == "linux":
        return "Linux"
    return system or "unknown"


def get_runtime_context():
    """Detect and return runtime environment information."""
    system = platform.system()
    os_name = _operating_system_name(system)
    shell_info = _detect_shell(system)

    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}."
        f"{sys.version_info.micro}"
    )
    architecture = platform.machine() or platform.processor() or "unknown"
    workspace_path = str(Path.cwd().resolve())

    return {
        "os": os_name,
        "shell": shell_info,
        "python_version": python_version,
        "architecture": architecture,
        "workspace_path": workspace_path,
        "platform_details": {
            "system": system,
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "processor": platform.processor(),
            "python_implementation": platform.python_implementation(),
        },
    }


def get_runtime_info():
    """Get runtime environment information as a read-only tool for the LLM."""
    return get_runtime_context()
