"""
Shared pytest fixtures for integration tests.

All tests spin up a real devcontainer and run commands inside it.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Generator

import pytest


class DevContainer:
    """Helper class to manage a devcontainer lifecycle."""

    def __init__(self, workspace_dir: str, config_path: Path):
        self.workspace_dir = workspace_dir
        self.config_path = config_path
        self._started = False

    def start(self) -> None:
        """Start the devcontainer."""
        result = subprocess.run(
            [
                "npx", "-y", "@devcontainers/cli", "up",
                "--workspace-folder", self.workspace_dir,
                "--config", str(self.config_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start container: {result.stderr}")
        self._started = True

    def exec(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Execute a command inside the container."""
        if not self._started:
            raise RuntimeError("Container not started")
        return subprocess.run(
            [
                "npx", "-y", "@devcontainers/cli", "exec",
                "--workspace-folder", self.workspace_dir,
                "--config", str(self.config_path),
                "bash", "-c", command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def stop(self) -> None:
        """Stop the devcontainer."""
        if self._started:
            subprocess.run(
                [
                    "npx", "-y", "@devcontainers/cli", "down",
                    "--workspace-folder", self.workspace_dir,
                    "--config", str(self.config_path),
                ],
                capture_output=True,
                timeout=60,
            )
            self._started = False


@pytest.fixture(scope="module")
def devcontainer() -> Generator[DevContainer, None, None]:
    """
    Fixture that starts a devcontainer for the test module.

    Yields a DevContainer instance that can be used to execute commands.
    Container is started once per module and stopped after all tests complete.
    """
    claude_dir = Path.home() / ".claude" / ".devcontainer"
    config_path = claude_dir / "devcontainer.json"

    if not config_path.exists():
        pytest.skip(f"devcontainer.json not found at {config_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        container = DevContainer(tmpdir, config_path)
        container.start()
        yield container
        container.stop()


@pytest.fixture
def git_repo(devcontainer: DevContainer) -> str:
    """
    Fixture that creates a temporary git repo inside the container.

    Returns the path to the repo inside the container.
    """
    # Create a temp dir and init git repo
    result = devcontainer.exec(
        "mktemp -d && cd $(mktemp -d) && git init && git config user.email 'test@test.com' && git config user.name 'Test' && pwd"
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to create git repo: {result.stderr}")
    return result.stdout.strip().split("\n")[-1]
