"""CLI entry points for ClankerCage."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

__all__ = ["main", "shell_remote"]


def get_embedded_devcontainer_dir() -> Path:
    """Get the path to embedded devcontainer files in the package."""
    return Path(__file__).parent / "devcontainer"


def get_workspace_dir() -> Path:
    """Get the fixed workspace directory for devcontainer files."""
    return Path.home() / ".cache" / "clankercage" / "workspace"


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
            "source=${localEnv:HOME}/.gnupg,target=/home/node/.gnupg,type=bind"
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
    return parser


def apply_env_defaults(args: argparse.Namespace) -> None:
    """Apply environment variable defaults to args."""
    args.ssh_key_file = args.ssh_key_file or os.environ.get("CLANKERCAGE_SSH_KEY")
    args.git_user_name = args.git_user_name or os.environ.get("CLANKERCAGE_GIT_USER_NAME")
    args.git_user_email = args.git_user_email or os.environ.get("CLANKERCAGE_GIT_USER_EMAIL")
    args.gh_token = args.gh_token or os.environ.get("CLANKERCAGE_GH_TOKEN")
    args.gpg_key_id = args.gpg_key_id or os.environ.get("CLANKERCAGE_GPG_KEY_ID")


def run_devcontainer(config_path: Path, workspace_dir: Path, project_dir: Path, claude_args: list[str], shell_cmd: str | None = None) -> None:
    """Run the devcontainer with claude or a shell command.

    Each invocation creates a new container with a unique instance ID,
    allowing multiple clanker instances to run simultaneously.
    """
    devcontainer_cmd = ["npx", "-y", "@devcontainers/cli"]

    # Generate unique instance ID for this container
    instance_id = uuid.uuid4().hex[:12]
    id_label = f"clanker.instance={instance_id}"

    if shell_cmd:
        run_cmd = ["bash", "-c", shell_cmd]
    else:
        run_cmd = ["claude", "--dangerously-skip-permissions"] + claude_args

    print(f"Starting devcontainer (instance {instance_id})...")

    up_cmd = devcontainer_cmd + [
        "up",
        "--workspace-folder", str(project_dir),
        "--config", str(config_path),
        "--id-label", id_label,
    ]

    subprocess.run(up_cmd, check=True)

    exec_cmd = devcontainer_cmd + [
        "exec",
        "--workspace-folder", str(project_dir),
        "--config", str(config_path),
        "--id-label", id_label,
    ] + run_cmd

    # Use execvp to replace process for clean TTY passthrough
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

    # Extract embedded devcontainer files to cache directory
    cache_dir = extract_devcontainer_files()
    devcontainer_dir = cache_dir / ".devcontainer"
    source_config = devcontainer_dir / "devcontainer.json"

    # Setup runtime directory for SSH config etc
    runtime_dir = Path.home() / ".claude" / "clankercage-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Load and modify config
    config = json.loads(source_config.read_text())
    config = modify_config(config, args, runtime_dir, devcontainer_dir, project_dir)

    # Write modified config back to the temp devcontainer dir
    runtime_config = devcontainer_dir / "devcontainer.json"
    runtime_config.write_text(json.dumps(config, indent=2))

    run_devcontainer(runtime_config, cache_dir, project_dir, claude_args, args.shell)


def shell_remote() -> None:
    """Alias for main() - for clankercage-remote entry point."""
    main()
