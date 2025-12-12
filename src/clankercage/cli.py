"""CLI entry points for ClankerCage."""

import argparse
import json
import os
import pty
import select
import shlex
import shutil
import subprocess
import sys
import termios
import threading
import tty
import uuid
from pathlib import Path

__all__ = ["main", "shell_remote"]


def get_embedded_devcontainer_dir() -> Path:
    """Get the path to embedded devcontainer files in the package."""
    return Path(__file__).parent / "devcontainer"


def get_workspace_dir(instance_id: str) -> Path:
    """Get instance-specific workspace directory for devcontainer files.

    Each instance gets its own directory to prevent race conditions when
    multiple ClankerCage instances run with different configurations.
    """
    return Path.home() / ".cache" / "clankercage" / f"workspace-{instance_id}"


def extract_devcontainer_files(instance_id: str) -> Path:
    """Extract embedded devcontainer files to an instance-specific cache directory."""
    workspace_dir = get_workspace_dir(instance_id)
    devcontainer_dir = workspace_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    pkg_dir = get_embedded_devcontainer_dir()
    for f in pkg_dir.iterdir():
        if f.is_file() and f.name != "__init__.py" and not f.name.endswith(".pyc"):
            shutil.copy2(f, devcontainer_dir / f.name)

    return workspace_dir


def generate_ssh_config(runtime_dir: Path, ssh_key_name: str) -> Path:
    """Generate SSH config file for GitHub."""
    ssh_config = runtime_dir / "ssh_config"
    ssh_config.write_text(f"""Host github.com
  HostName github.com
  User git
  IdentityFile /home/node/.ssh/{ssh_key_name}
  IdentitiesOnly yes
""")
    # SSH requires strict permissions on config files
    ssh_config.chmod(0o644)
    return ssh_config


def modify_config(config: dict, args: argparse.Namespace, runtime_dir: Path, devcontainer_dir: Path | None = None, project_dir: Path | None = None) -> dict:
    """Modify devcontainer config with user-specific settings."""

    # If --build flag, replace image with build config
    if args.build and devcontainer_dir:
        config.pop("image", None)
        config["build"] = {"dockerfile": "Dockerfile", "context": "."}

    # Mount the actual project directory (where user ran clankercage from)
    if project_dir:
        config["workspaceMount"] = f"source={project_dir},target=/workspace,type=bind,consistency=delegated"

    # Replace .claude docker volume with read-only bind mount for security
    # This prevents container from modifying settings, hooks, or stealing API keys
    if "mounts" in config:
        config["mounts"] = [
            m.replace(
                "source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume",
                "source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind,readonly"
            ) if "claude-code-config" in m else m
            for m in config["mounts"]
        ]

    # Filter out existing SSH and GPG mounts
    if "mounts" in config:
        config["mounts"] = [
            m for m in config["mounts"]
            if ".ssh/" not in m and ".gnupg" not in m
        ]

    # Add SSH mounts if key provided
    if args.ssh_key_file:
        ssh_key_path = Path(args.ssh_key_file).resolve()
        ssh_key_name = ssh_key_path.name
        ssh_config_path = generate_ssh_config(runtime_dir, ssh_key_name)

        config.setdefault("mounts", [])
        config["mounts"].append(
            f"source={ssh_key_path},target=/home/node/.ssh/{ssh_key_name},type=bind,readonly"
        )
        config["mounts"].append(
            f"source={ssh_config_path},target=/home/node/.ssh/config,type=bind,readonly"
        )

    # Add GPG mount if key ID provided
    if args.gpg_key_id:
        config.setdefault("mounts", [])
        config["mounts"].append(
            "source=${localEnv:HOME}/.gnupg,target=/home/node/.gnupg,type=bind,readonly"
        )

    # Build postStartCommand
    commands = ["sudo /usr/local/bin/init-firewall.sh"]

    if args.git_user_name:
        commands.append(f"git config --global user.name {shlex.quote(args.git_user_name)}")

    if args.git_user_email:
        commands.append(f"git config --global user.email {shlex.quote(args.git_user_email)}")

    if args.gpg_key_id:
        commands.append(f"git config --global user.signingkey {shlex.quote(args.gpg_key_id)}")
        commands.append("git config --global commit.gpgsign true")
        commands.append("git config --global gpg.program gpg")
        commands.append("gpg-connect-agent /bye >/dev/null 2>&1 || true")

    if args.gh_token:
        commands.append(f"echo {shlex.quote(args.gh_token)} | gh auth login --with-token")

    config["postStartCommand"] = " && ".join(commands)

    return config


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="Run Claude Code in a sandboxed devcontainer",
        epilog="Any additional arguments are passed to claude."
    )
    parser.add_argument("--ssh-key-file", help="Path to SSH private key")
    parser.add_argument("--git-user-name", help="Git user.name")
    parser.add_argument("--git-user-email", help="Git user.email")
    parser.add_argument("--gh-token", help="GitHub token")
    parser.add_argument("--gpg-key-id", help="GPG key ID for signing")
    parser.add_argument("--build", action="store_true", help="Build from local Dockerfile instead of using pre-built image")
    parser.add_argument("--shell", metavar="CMD", help="Run a shell command instead of claude (for testing)")
    parser.add_argument("--safe-mode", action="store_true", help="Run Claude with permission prompts enabled (more interruptions, extra safety)")
    return parser


def apply_env_defaults(args: argparse.Namespace) -> None:
    """Apply environment variable defaults to args."""
    args.ssh_key_file = args.ssh_key_file or os.environ.get("CLANKERCAGE_SSH_KEY")
    args.git_user_name = args.git_user_name or os.environ.get("CLANKERCAGE_GIT_USER_NAME")
    args.git_user_email = args.git_user_email or os.environ.get("CLANKERCAGE_GIT_USER_EMAIL")
    args.gh_token = args.gh_token or os.environ.get("CLANKERCAGE_GH_TOKEN")
    args.gpg_key_id = args.gpg_key_id or os.environ.get("CLANKERCAGE_GPG_KEY_ID")


class InputBuffer:
    """Thread-safe buffer for capturing stdin during startup."""

    def __init__(self):
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.capturing = True

    def append(self, data: bytes) -> None:
        with self.lock:
            if self.capturing:
                self.buffer.extend(data)

    def stop_and_get(self) -> bytes:
        with self.lock:
            self.capturing = False
            return bytes(self.buffer)


def run_subprocess_with_input_capture(cmd: list[str], input_buffer: InputBuffer) -> bytes:
    """Run a subprocess while capturing any stdin typed during execution.

    Uses a PTY so the subprocess gets proper terminal output, while we
    intercept stdin in raw mode to buffer it for later replay.

    Returns the captured input bytes.
    """
    old_settings = termios.tcgetattr(sys.stdin.fileno())

    # Create PTY for the subprocess
    master_fd, slave_fd = pty.openpty()

    proc = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    # Put our terminal in raw mode to capture keystrokes
    tty.setraw(sys.stdin.fileno())

    try:
        while proc.poll() is None:
            readable, _, _ = select.select([master_fd, sys.stdin.fileno()], [], [], 0.1)

            # Forward subprocess output to our stdout
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 1024)
                    if data:
                        os.write(sys.stdout.fileno(), data)
                except OSError:
                    break

            # Capture any user input (don't forward to subprocess)
            if sys.stdin.fileno() in readable:
                try:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if data:
                        input_buffer.append(data)
                except OSError:
                    break

        # Drain remaining output
        while True:
            readable, _, _ = select.select([master_fd], [], [], 0.1)
            if not readable:
                break
            try:
                data = os.read(master_fd, 1024)
                if not data:
                    break
                os.write(sys.stdout.fileno(), data)
            except OSError:
                break

    finally:
        os.close(master_fd)
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    return input_buffer.stop_and_get()


def run_with_pty(cmd: list[str], buffered_input: bytes) -> int:
    """Run command in a PTY, injecting buffered input.

    This preserves full TTY behavior (colors, cursor, raw mode) while
    allowing us to inject any input that was typed during startup.
    """
    # Save original terminal settings
    old_settings = None
    if sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin.fileno())

    master_fd, slave_fd = pty.openpty()
    pid = os.fork()

    if pid == 0:
        # Child process
        os.close(master_fd)
        os.setsid()

        # Set up slave as controlling terminal
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        os.execvp(cmd[0], cmd)

    # Parent process
    os.close(slave_fd)

    # Put terminal in raw mode for proper passthrough
    if sys.stdin.isatty():
        tty.setraw(sys.stdin.fileno())

    # Inject buffered input first
    if buffered_input:
        os.write(master_fd, buffered_input)

    try:
        while True:
            readable, _, _ = select.select([master_fd, sys.stdin.fileno()], [], [], 0.1)

            if master_fd in readable:
                try:
                    data = os.read(master_fd, 1024)
                    if not data:
                        break
                    os.write(sys.stdout.fileno(), data)
                except OSError:
                    break

            if sys.stdin.fileno() in readable:
                try:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if data:
                        os.write(master_fd, data)
                except OSError:
                    break

            # Check if child has exited
            result = os.waitpid(pid, os.WNOHANG)
            if result[0] != 0:
                # Drain any remaining output
                while True:
                    readable, _, _ = select.select([master_fd], [], [], 0.1)
                    if not readable:
                        break
                    try:
                        data = os.read(master_fd, 1024)
                        if not data:
                            break
                        os.write(sys.stdout.fileno(), data)
                    except OSError:
                        break
                break

    finally:
        os.close(master_fd)
        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

    # Get exit status
    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 1


def run_devcontainer(config_path: Path, workspace_dir: Path, project_dir: Path, claude_args: list[str], shell_cmd: str | None = None, safe_mode: bool = False, instance_id: str | None = None) -> None:
    """Run the devcontainer with claude or a shell command.

    Each invocation uses a unique instance ID for both the config directory
    and container label, allowing multiple clanker instances to run simultaneously.

    Input typed during container startup is buffered and replayed once ready.
    """
    devcontainer_cmd = ["npx", "-y", "@devcontainers/cli"]

    # Use provided instance ID or generate one (for backwards compatibility)
    if instance_id is None:
        instance_id = uuid.uuid4().hex[:12]
    id_label = f"clanker.instance={instance_id}"

    if shell_cmd:
        run_cmd = ["bash", "-c", shell_cmd]
    elif safe_mode:
        run_cmd = ["claude"] + claude_args
    else:
        run_cmd = ["claude", "--dangerously-skip-permissions"] + claude_args

    print(f"Starting devcontainer (instance {instance_id})...")

    up_cmd = devcontainer_cmd + [
        "up",
        "--workspace-folder", str(project_dir),
        "--config", str(config_path),
        "--id-label", id_label,
    ]

    # Run devcontainer up while capturing any stdin typed during startup
    input_buffer = InputBuffer()
    buffered_input = b""

    if sys.stdin.isatty():
        buffered_input = run_subprocess_with_input_capture(up_cmd, input_buffer)
    else:
        subprocess.run(up_cmd, check=True)

    if buffered_input:
        print(f"(Replaying {len(buffered_input)} bytes of buffered input)")

    exec_cmd = devcontainer_cmd + [
        "exec",
        "--workspace-folder", str(project_dir),
        "--config", str(config_path),
        "--id-label", id_label,
    ] + run_cmd

    # Run with PTY to preserve terminal behavior, injecting buffered input
    if sys.stdin.isatty():
        exit_code = run_with_pty(exec_cmd, buffered_input)
        sys.exit(exit_code)
    else:
        # Non-TTY mode: use execvp as before
        os.execvp("npx", exec_cmd)


IMAGE_NAME = "ghcr.io/clankerbot/clankercage:latest"


def get_container_info(image_name: str) -> dict:
    """Get container build info from Docker image labels.

    Returns dict with 'build_time' and 'source' keys.
    """
    result = subprocess.run(
        ["docker", "image", "inspect", image_name, "--format",
         '{{index .Config.Labels "org.opencontainers.image.created"}}|{{index .Config.Labels "org.opencontainers.image.source.type"}}'],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return {"build_time": "unknown", "source": "unknown"}

    parts = result.stdout.strip().split("|")
    build_time = parts[0] if parts[0] else "unknown"
    source = parts[1] if len(parts) > 1 and parts[1] else "local"

    return {"build_time": build_time, "source": source}


def print_container_info(image_name: str) -> None:
    """Print container build information on startup."""
    info = get_container_info(image_name)

    source_display = "GitHub Container Registry (ghcr.io)" if info["source"] == "ghcr.io" else "Local build"
    build_time_display = info["build_time"] if info["build_time"] != "unknown" else "Unknown"

    print(f"Container image: {image_name}")
    print(f"  Built: {build_time_display}")
    print(f"  Source: {source_display}")
    print()


def check_docker_accessible() -> None:
    """Check if Docker is running and accessible. Exit with error if not."""
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(
            "\n"
            "╔════════════════════════════════════════════════════════════════╗\n"
            "║  ERROR: Docker is not running or not accessible               ║\n"
            "╠════════════════════════════════════════════════════════════════╣\n"
            "║  ClankerCage requires Docker to run.                          ║\n"
            "║                                                                ║\n"
            "║  Please ensure:                                               ║\n"
            "║    1. Docker is installed                                     ║\n"
            "║    2. Docker daemon is running                                ║\n"
            "║    3. You have permission to access Docker                    ║\n"
            "║       (try: sudo usermod -aG docker $USER)                    ║\n"
            "╚════════════════════════════════════════════════════════════════╝\n",
            file=sys.stderr
        )
        sys.exit(1)


def pull_docker_image_if_needed() -> None:
    """Pull the Docker image if not already present."""
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE_NAME],
        capture_output=True
    )
    if result.returncode != 0:
        print("Pulling Docker image...")
        subprocess.run(["docker", "pull", IMAGE_NAME], check=True)


def main() -> None:
    """
    Main entry point - runs Claude Code in a sandboxed devcontainer.

    Uses embedded devcontainer files from the package.
    With --build, builds from Dockerfile. Without, uses pre-built image.
    """
    parser = create_parser()
    args, claude_args = parser.parse_known_args()
    apply_env_defaults(args)

    if args.ssh_key_file and not Path(args.ssh_key_file).exists():
        print(f"Error: SSH key not found at {args.ssh_key_file}", file=sys.stderr)
        sys.exit(1)

    # Check Docker is running before proceeding
    check_docker_accessible()

    # Pull image if not building locally and image doesn't exist
    if not args.build:
        pull_docker_image_if_needed()
        print_container_info(IMAGE_NAME)
    else:
        print("Container image: Local build (--build flag)")
        print()

    # Capture current working directory (the project to mount)
    project_dir = Path.cwd().resolve()

    # Generate unique instance ID early - used for both cache dir and container ID
    instance_id = uuid.uuid4().hex[:12]

    # Extract embedded devcontainer files to instance-specific cache directory
    # This prevents race conditions when multiple instances run concurrently
    cache_dir = extract_devcontainer_files(instance_id)
    devcontainer_dir = cache_dir / ".devcontainer"
    source_config = devcontainer_dir / "devcontainer.json"

    # Setup runtime directory for SSH config etc (shared, not instance-specific)
    runtime_dir = Path.home() / ".claude" / "clankercage-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Load and modify config
    config = json.loads(source_config.read_text())
    config = modify_config(config, args, runtime_dir, devcontainer_dir, project_dir)

    # Write modified config back to the temp devcontainer dir
    runtime_config = devcontainer_dir / "devcontainer.json"
    runtime_config.write_text(json.dumps(config, indent=2))

    run_devcontainer(runtime_config, cache_dir, project_dir, claude_args, args.shell, args.safe_mode, instance_id)


def shell_remote() -> None:
    """Alias for main() - for clankercage-remote entry point."""
    main()
