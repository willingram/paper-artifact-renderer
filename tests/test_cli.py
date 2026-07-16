from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import sys

import pytest

from paper_artifact_renderer import __version__

SUPPORTED_COMMANDS = ("par", "paper-artifact-renderer")


def run_command(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True)


@pytest.mark.parametrize("command", SUPPORTED_COMMANDS)
@pytest.mark.parametrize("option", ("--help", "--version"))
def test_console_script_help_and_version(command: str, option: str) -> None:
    executable = shutil.which(command)
    assert executable is not None, f"{command} is not installed"

    result = run_command(executable, option)

    assert result.returncode == 0, result.stderr
    if option == "--help":
        assert result.stdout.startswith("usage: par ")
    else:
        assert result.stdout.strip() == f"par {__version__}"


@pytest.mark.parametrize("option", ("--help", "--version"))
def test_module_help_and_version(option: str) -> None:
    result = run_command(sys.executable, "-m", "paper_artifact_renderer", option)

    assert result.returncode == 0, result.stderr
    if option == "--help":
        assert result.stdout.startswith("usage: par ")
    else:
        assert result.stdout.strip() == f"par {__version__}"


def test_distribution_declares_only_supported_console_scripts() -> None:
    distribution = importlib.metadata.distribution("paper-artifact-renderer")
    console_scripts = {entry_point.name for entry_point in distribution.entry_points if entry_point.group == "console_scripts"}

    assert console_scripts == set(SUPPORTED_COMMANDS)
