"""
Tests for the clanker CLI.

These tests verify that:
- The CLI correctly mounts local directories
- The --shell flag works for non-interactive testing
- SSH mount warnings work correctly
"""

import argparse
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from clanker.cli import (
    get_existing_container,
    container_has_ssh_mounts,
    warn_if_ssh_mount_missing,
)


def run_clanker(
    project_dir: Path,
    shell_cmd: str,
    timeout: int = 120,
    ssh_key_file: str | None = None,
    build: bool = False,
) -> subprocess.CompletedProcess:
    """Run clanker-shell with --shell in a given project directory."""
    cmd = ["uv", "run", "clanker-shell", "--shell", shell_cmd]

    if build:
        cmd.append("--build")

    if ssh_key_file:
        cmd.extend(["--ssh-key-file", ssh_key_file])

    return subprocess.run(
        cmd,
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def describe_workspace_mounting():
    """Tests for workspace directory mounting."""

    @pytest.mark.integration
    def it_mounts_local_directory_to_workspace(tmp_path: Path):
        """Verify that the local directory is mounted at /workspace in the container."""
        # Create a unique file in the temp directory
        marker = f"clanker-test-{uuid.uuid4()}"
        marker_file = tmp_path / "test-marker.txt"
        marker_file.write_text(marker)

        # Run clanker and check if the file exists in /workspace
        result = run_clanker(tmp_path, "cat /workspace/test-marker.txt")

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert marker in result.stdout, (
            f"Expected marker '{marker}' not found in output: {result.stdout}"
        )

    @pytest.mark.integration
    def it_can_write_files_back_to_host(tmp_path: Path):
        """Verify that files written in /workspace appear on the host."""
        marker = f"written-from-container-{uuid.uuid4()}"
        output_file = "output.txt"

        # Write a file from inside the container
        result = run_clanker(tmp_path, f"echo '{marker}' > /workspace/{output_file}")

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify the file exists on the host
        host_file = tmp_path / output_file
        assert host_file.exists(), f"File not created on host: {host_file}"
        assert marker in host_file.read_text(), (
            f"Expected marker not in file contents: {host_file.read_text()}"
        )

    @pytest.mark.integration
    def it_preserves_file_permissions(tmp_path: Path):
        """Verify that file permissions are preserved through the mount."""
        script = tmp_path / "test-script.sh"
        script.write_text("#!/bin/bash\necho 'hello'")
        script.chmod(0o755)

        # Check the file is executable inside the container
        result = run_clanker(tmp_path, "test -x /workspace/test-script.sh && echo 'executable'")

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert "executable" in result.stdout, (
            f"File not executable in container: {result.stdout}"
        )

    @pytest.mark.integration
    def it_shows_correct_working_directory(tmp_path: Path):
        """Verify that pwd shows /workspace."""
        result = run_clanker(tmp_path, "pwd")

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert "/workspace" in result.stdout, (
            f"Expected /workspace, got: {result.stdout}"
        )


def describe_docker_access():
    """Tests for Docker socket access."""

    @pytest.mark.integration
    def it_can_access_docker_socket(tmp_path: Path):
        """Verify that docker commands work inside the container."""
        result = run_clanker(tmp_path, "docker ps --format '{{.ID}}' | head -1")

        assert result.returncode == 0, f"Docker command failed: {result.stderr}"
        # Should return at least one container ID (the clanker container itself)
        # or empty if no containers running - either is fine, just shouldn't error


def describe_installed_tools():
    """Tests for tools that should be available in the container."""

    @pytest.mark.integration
    def it_has_docker_available(tmp_path: Path):
        """Verify docker CLI is installed and can connect to daemon."""
        result = run_clanker(tmp_path, "docker --version && docker info --format '{{.ServerVersion}}'")

        assert result.returncode == 0, f"Docker not available: {result.stderr}"
        assert "Docker version" in result.stdout, f"Unexpected docker output: {result.stdout}"

    @pytest.mark.integration
    def it_has_uv_available(tmp_path: Path):
        """Verify uv is installed."""
        result = run_clanker(tmp_path, "uv --version")

        assert result.returncode == 0, f"uv not available: {result.stderr}"
        assert "uv" in result.stdout, f"Unexpected uv output: {result.stdout}"

    @pytest.mark.integration
    def it_has_uvx_available(tmp_path: Path):
        """Verify uvx is installed."""
        result = run_clanker(tmp_path, "uvx --version")

        assert result.returncode == 0, f"uvx not available: {result.stderr}"

    @pytest.mark.integration
    def it_has_npm_available(tmp_path: Path):
        """Verify npm is installed."""
        result = run_clanker(tmp_path, "npm --version")

        assert result.returncode == 0, f"npm not available: {result.stderr}"

    @pytest.mark.integration
    def it_has_pnpm_available(tmp_path: Path):
        """Verify pnpm is installed."""
        result = run_clanker(tmp_path, "pnpm --version")

        assert result.returncode == 0, f"pnpm not available: {result.stderr}"

    @pytest.mark.integration
    def it_has_playwright_available(tmp_path: Path):
        """Verify playwright is installed and browsers are available."""
        result = run_clanker(tmp_path, "npx playwright --version")

        assert result.returncode == 0, f"Playwright not available: {result.stderr}"
        assert "Version" in result.stdout or result.stdout.strip(), (
            f"Unexpected playwright output: {result.stdout}"
        )

    @pytest.mark.integration
    def it_can_run_playwright_chromium(tmp_path: Path):
        """Verify playwright can launch chromium browser."""
        # Use npx playwright to test browser launch via screenshot
        # This verifies both playwright and chromium are working
        result = run_clanker(
            tmp_path,
            "npx playwright screenshot --browser chromium about:blank /workspace/test.png && ls -la /workspace/test.png",
            timeout=60,
        )

        assert result.returncode == 0, f"Playwright chromium failed: {result.stderr}"
        assert "test.png" in result.stdout, f"Screenshot not created: {result.stdout}"


@pytest.fixture(scope="module")
def ssh_server(tmp_path_factory):
    """Start a local SSH server with a generated keypair.

    Mimics GitHub: accepts key auth, host key must be in known_hosts.
    """
    import time

    tmp_path = tmp_path_factory.mktemp("ssh")

    # Generate keypair
    private_key = tmp_path / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(private_key), "-N", "", "-q"],
        check=True,
    )
    private_key.chmod(0o600)

    # Setup authorized_keys
    ssh_dir = tmp_path / "server_ssh"
    ssh_dir.mkdir()
    (ssh_dir / "authorized_keys").write_text((tmp_path / "id_ed25519.pub").read_text())

    # Start SSH server
    container_name = f"test-sshd-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker", "run", "-d",
            "--name", container_name,
            "-e", "PUID=1000", "-e", "PGID=1000",
            "-e", "USER_NAME=git",
            "-e", "PASSWORD_ACCESS=false",
            "-v", f"{ssh_dir}:/config/.ssh",
            "lscr.io/linuxserver/openssh-server:latest",
        ],
        check=True,
        capture_output=True,
    )

    # Wait for sshd
    for _ in range(30):
        if subprocess.run(["docker", "exec", container_name, "pgrep", "-f", "sshd"], capture_output=True).returncode == 0:
            break
        time.sleep(1)
    time.sleep(2)

    # Get container IP
    ip = subprocess.run(
        ["docker", "inspect", container_name, "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    yield {"key": str(private_key), "ip": ip, "port": 2222, "container": container_name}

    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)


def describe_ssh():
    """SSH test using a local SSH server that mimics GitHub's behavior."""

    @pytest.mark.integration
    def it_can_ssh_to_server_via_clanker(tmp_path: Path, ssh_server):
        """Test SSH via clanker CLI - mirrors: uv run clanker --ssh-key-file KEY --shell 'ssh -T git@server'.

        This test MUST use the real clanker CLI, not docker run directly.
        If this test passes but the real command fails, the test is wrong.

        NOTE: SSH mounts must be specified from the FIRST run. If a container is started
        without --ssh-key-file, adding it later won't update the existing container's mounts.
        This is a Docker limitation - mounts can't be added to running containers.
        """
        # Copy SSH private key to tmp_path (will be passed to --ssh-key-file)
        ssh_key = tmp_path / "id_ed25519"
        ssh_key.write_text(Path(ssh_server["key"]).read_text())
        ssh_key.chmod(0o600)

        # Get server's host key and save to workspace (mounted at /workspace)
        keyscan = subprocess.run(
            ["ssh-keyscan", "-p", str(ssh_server["port"]), ssh_server["ip"]],
            capture_output=True, text=True,
        )
        known_hosts = tmp_path / "server_known_hosts"
        known_hosts.write_text(keyscan.stdout)

        # Run clanker WITH --ssh-key-file from the start
        result = run_clanker(
            tmp_path,
            f"cat /workspace/server_known_hosts >> ~/.ssh/known_hosts && "
            f"ssh -T -i /home/node/.ssh/id_ed25519 -p {ssh_server['port']} git@{ssh_server['ip']} echo success",
            ssh_key_file=str(ssh_key),
            build=True,
            timeout=300,
        )

        assert result.returncode == 0, (
            f"SSH via clanker failed.\nstderr: {result.stderr}\nstdout: {result.stdout}"
        )
        assert "success" in result.stdout, (
            f"Expected 'success' in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def describe_ssh_mount_warning():
    """Unit tests for SSH mount warning functionality."""

    def describe_get_existing_container():
        """Tests for get_existing_container function."""

        def it_returns_container_id_when_exists():
            """Should return container ID when a matching container exists."""
            with patch("clanker.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="abc123def456\n",
                    returncode=0
                )
                result = get_existing_container(Path("/test/project"))

                assert result == "abc123def456"
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "docker" in call_args
                assert "label=devcontainer.local_folder=/test/project" in call_args

        def it_returns_none_when_no_container():
            """Should return None when no matching container exists."""
            with patch("clanker.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="",
                    returncode=0
                )
                result = get_existing_container(Path("/test/project"))

                assert result is None

    def describe_container_has_ssh_mounts():
        """Tests for container_has_ssh_mounts function."""

        def it_returns_true_when_ssh_key_mounted():
            """Should return True when container has SSH key mount."""
            mounts_json = '[{"Destination": "/home/node/.ssh/id_ed25519"}]'
            with patch("clanker.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout=mounts_json,
                    returncode=0
                )
                result = container_has_ssh_mounts("abc123")

                assert result is True

        def it_returns_false_when_no_ssh_key_mounted():
            """Should return False when container only has .ssh directory but no key."""
            mounts_json = '[{"Destination": "/home/node/.ssh"}]'
            with patch("clanker.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout=mounts_json,
                    returncode=0
                )
                result = container_has_ssh_mounts("abc123")

                assert result is False

        def it_returns_false_when_no_ssh_mounts():
            """Should return False when container has no SSH mounts at all."""
            mounts_json = '[{"Destination": "/workspace"}, {"Destination": "/home/node/.claude"}]'
            with patch("clanker.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout=mounts_json,
                    returncode=0
                )
                result = container_has_ssh_mounts("abc123")

                assert result is False

        def it_returns_false_on_docker_error():
            """Should return False when docker inspect fails."""
            with patch("clanker.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="",
                    returncode=1
                )
                result = container_has_ssh_mounts("abc123")

                assert result is False

        def it_returns_false_on_invalid_json():
            """Should return False when docker returns invalid JSON."""
            with patch("clanker.cli.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="not valid json",
                    returncode=0
                )
                result = container_has_ssh_mounts("abc123")

                assert result is False

    def describe_warn_if_ssh_mount_missing():
        """Tests for warn_if_ssh_mount_missing function."""

        def it_does_nothing_when_no_ssh_key_specified():
            """Should not warn when no SSH key is specified."""
            args = argparse.Namespace(ssh_key_file=None)
            with patch("clanker.cli.get_existing_container") as mock_get:
                warn_if_ssh_mount_missing(args, Path("/test"))
                mock_get.assert_not_called()

        def it_does_nothing_when_no_existing_container():
            """Should not warn when no existing container."""
            args = argparse.Namespace(ssh_key_file="/path/to/key")
            with patch("clanker.cli.get_existing_container", return_value=None):
                with patch("clanker.cli.container_has_ssh_mounts") as mock_has:
                    warn_if_ssh_mount_missing(args, Path("/test"))
                    mock_has.assert_not_called()

        def it_does_nothing_when_container_has_ssh_mounts():
            """Should not warn when container already has SSH mounts."""
            args = argparse.Namespace(ssh_key_file="/path/to/key")
            with patch("clanker.cli.get_existing_container", return_value="abc123"):
                with patch("clanker.cli.container_has_ssh_mounts", return_value=True):
                    with patch("builtins.print") as mock_print:
                        warn_if_ssh_mount_missing(args, Path("/test"))
                        mock_print.assert_not_called()

        def it_warns_when_ssh_key_but_no_mounts(capsys):
            """Should print warning when SSH key specified but container lacks mounts."""
            args = argparse.Namespace(ssh_key_file="/path/to/key")
            with patch("clanker.cli.get_existing_container", return_value="abc123"):
                with patch("clanker.cli.container_has_ssh_mounts", return_value=False):
                    warn_if_ssh_mount_missing(args, Path("/test"))

            captured = capsys.readouterr()
            assert "WARNING" in captured.err
            assert "SSH key specified" in captured.err
            assert "docker rm -f abc123" in captured.err
