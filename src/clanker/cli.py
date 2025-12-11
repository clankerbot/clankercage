"""CLI entry points for clanker."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["main", "install"]


def get_embedded_devcontainer_dir() -> Path:
    """Get the path to embedded devcontainer files in the package."""
    return Path(__file__).parent / "devcontainer"


def get_workspace_dir() -> Path:
    """Get the fixed workspace directory for devcontainer files."""
    return Path.home() / ".cache" / "clanker" / "workspace"


def extract_devcontainer_files() -> Path:
    """Extract embedded devcontainer files to a fixed cache directory."""
    workspace_dir = get_workspace_dir()
    devcontainer_dir = workspace_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    pkg_dir = get_embedded_devcontainer_dir()
    for f in pkg_dir.iterdir():
        if f.is_file() and f.name != "__init__.py" and not f.name.endswith(".pyc"):
            shutil.copy2(f, devcontainer_dir / f.name)

    return workspace_dir


def get_docker_socket_gid() -> str | None:
    """Get the GID of the docker socket if it exists."""
    socket_path = Path("/var/run/docker.sock")
    if socket_path.is_socket():
        try:
            return str(os.stat(socket_path).st_gid)
        except OSError:
            pass
    return None


def generate_ssh_config(runtime_dir: Path, ssh_key_name: str) -> Path:
    """Generate SSH config file for GitHub."""
    ssh_config = runtime_dir / "ssh_config"
    ssh_config.write_text(f"""Host github.com
  HostName github.com
  User git
  IdentityFile /home/node/.ssh/{ssh_key_name}
  IdentitiesOnly yes
""")
    return ssh_config


def modify_config(config: dict, args: argparse.Namespace, runtime_dir: Path, devcontainer_dir: Path | None = None, project_dir: Path | None = None) -> dict:
    """Modify devcontainer config with user-specific settings."""

    # If --build flag, replace image with build config
    if args.build and devcontainer_dir:
        config.pop("image", None)
        config["build"] = {"dockerfile": "Dockerfile", "context": "."}

    # Mount the actual project directory (where user ran clanker from)
    if project_dir:
        config["workspaceMount"] = f"source={project_dir},target=/workspace,type=bind,consistency=delegated"

    # Replace .claude docker volume with bind mount
    if "mounts" in config:
        config["mounts"] = [
            m.replace(
                "source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume",
                "source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind"
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
            "source=${localEnv:HOME}/.gnupg,target=/home/node/.gnupg,type=bind"
        )

    # Add docker group to runArgs if socket exists
    docker_gid = get_docker_socket_gid()
    if docker_gid:
        config.setdefault("runArgs", [])
        if "--group-add" not in config["runArgs"]:
            config["runArgs"].extend(["--group-add", docker_gid])

    # Build postStartCommand
    commands = ["sudo /usr/local/bin/init-firewall.sh"]

    if args.git_user_name:
        commands.append(f"git config --global user.name '{args.git_user_name}'")

    if args.git_user_email:
        commands.append(f"git config --global user.email '{args.git_user_email}'")

    if args.gpg_key_id:
        commands.append(f"git config --global user.signingkey '{args.gpg_key_id}'")
        commands.append("git config --global commit.gpgsign true")
        commands.append("git config --global gpg.program gpg")
        commands.append("gpg-connect-agent /bye >/dev/null 2>&1 || true")

    if args.gh_token:
        commands.append(f"echo '{args.gh_token}' | gh auth login --with-token")

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
    return parser


def apply_env_defaults(args: argparse.Namespace) -> None:
    """Apply environment variable defaults to args."""
    args.ssh_key_file = args.ssh_key_file or os.environ.get("CLANKER_SSH_KEY")
    args.git_user_name = args.git_user_name or os.environ.get("CLANKER_GIT_USER_NAME")
    args.git_user_email = args.git_user_email or os.environ.get("CLANKER_GIT_USER_EMAIL")
    args.gh_token = args.gh_token or os.environ.get("CLANKER_GH_TOKEN")
    args.gpg_key_id = args.gpg_key_id or os.environ.get("CLANKER_GPG_KEY_ID")


def run_devcontainer(config_path: Path, workspace_dir: Path, project_dir: Path, claude_args: list[str], shell_cmd: str | None = None) -> None:
    """Run the devcontainer with claude or a shell command."""
    devcontainer_cmd = ["npx", "-y", "@devcontainers/cli"]

    if shell_cmd:
        run_cmd = ["bash", "-c", shell_cmd]
    else:
        run_cmd = ["claude", "--dangerously-skip-permissions"] + claude_args

    exec_cmd = devcontainer_cmd + [
        "exec",
        "--workspace-folder", str(project_dir),
        "--config", str(config_path),
    ] + run_cmd

    result = subprocess.run(exec_cmd, stderr=subprocess.DEVNULL)

    if result.returncode != 0:
        print("Starting devcontainer...")

        up_cmd = devcontainer_cmd + [
            "up",
            "--workspace-folder", str(project_dir),
            "--config", str(config_path),
        ]

        subprocess.run(up_cmd, check=True)

        # Use execvp to replace process for clean TTY passthrough
        os.execvp("npx", exec_cmd)


IMAGE_NAME = "ghcr.io/clankerbot/clanker:latest"


def get_existing_container(project_dir: Path) -> str | None:
    """Get the container ID for an existing devcontainer for this project."""
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"label=devcontainer.local_folder={project_dir}", "-q"],
        capture_output=True, text=True
    )
    container_id = result.stdout.strip()
    return container_id if container_id else None


def container_has_ssh_mounts(container_id: str) -> bool:
    """Check if container has SSH key mounts."""
    result = subprocess.run(
        ["docker", "inspect", container_id, "--format", "{{json .Mounts}}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False
    try:
        mounts = json.loads(result.stdout)
        for mount in mounts:
            dest = mount.get("Destination", "")
            if ".ssh/" in dest and dest != "/home/node/.ssh":
                return True
    except (json.JSONDecodeError, TypeError):
        pass
    return False


def warn_if_ssh_mount_missing(args: argparse.Namespace, project_dir: Path) -> None:
    """Warn if SSH key requested but existing container lacks SSH mounts."""
    if not args.ssh_key_file:
        return

    container_id = get_existing_container(project_dir)
    if not container_id:
        return

    if not container_has_ssh_mounts(container_id):
        print(
            "\n⚠️  WARNING: SSH key specified but existing container lacks SSH mounts.\n"
            "   The SSH key will NOT be available inside the container.\n"
            "   To fix: remove the container and restart:\n"
            f"   docker rm -f {container_id}\n",
            file=sys.stderr
        )


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

    # Pull image if not building locally and image doesn't exist
    if not args.build:
        pull_docker_image_if_needed()

    # Capture current working directory (the project to mount)
    project_dir = Path.cwd().resolve()

    # Warn if SSH key requested but existing container lacks mounts
    warn_if_ssh_mount_missing(args, project_dir)

    # Extract embedded devcontainer files to cache directory
    cache_dir = extract_devcontainer_files()
    devcontainer_dir = cache_dir / ".devcontainer"
    source_config = devcontainer_dir / "devcontainer.json"

    # Setup runtime directory for SSH config etc
    runtime_dir = Path.home() / ".claude" / "clanker-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Load and modify config
    config = json.loads(source_config.read_text())
    config = modify_config(config, args, runtime_dir, devcontainer_dir, project_dir)

    # Write modified config back to the temp devcontainer dir
    runtime_config = devcontainer_dir / "devcontainer.json"
    runtime_config.write_text(json.dumps(config, indent=2))

    run_devcontainer(runtime_config, cache_dir, project_dir, claude_args, args.shell)


def install() -> None:
    """Alias for main() - kept for backwards compatibility."""
    main()
