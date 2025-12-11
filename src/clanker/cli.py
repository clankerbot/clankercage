"""CLI entry points for clanker."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

__all__ = ["main", "install"]


def get_embedded_devcontainer_dir() -> Path:
    """Get the path to embedded devcontainer files in the package."""
    return Path(__file__).parent / "devcontainer"


def extract_devcontainer_to_temp() -> Path:
    """Extract embedded devcontainer files to a temp directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="clanker-"))
    devcontainer_dir = temp_dir / ".devcontainer"
    devcontainer_dir.mkdir()

    pkg_dir = get_embedded_devcontainer_dir()
    for f in pkg_dir.iterdir():
        if f.is_file() and f.name != "__init__.py" and not f.name.endswith(".pyc"):
            shutil.copy2(f, devcontainer_dir / f.name)

    return temp_dir


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


def modify_config(config: dict, args: argparse.Namespace, runtime_dir: Path, devcontainer_dir: Path | None = None) -> dict:
    """Modify devcontainer config with user-specific settings."""

    # If --build flag, replace image with build config
    if args.build and devcontainer_dir:
        config.pop("image", None)
        config["build"] = {"dockerfile": "Dockerfile", "context": "."}

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
    return parser


def apply_env_defaults(args: argparse.Namespace) -> None:
    """Apply environment variable defaults to args."""
    args.ssh_key_file = args.ssh_key_file or os.environ.get("CLANKER_SSH_KEY")
    args.git_user_name = args.git_user_name or os.environ.get("CLANKER_GIT_USER_NAME")
    args.git_user_email = args.git_user_email or os.environ.get("CLANKER_GIT_USER_EMAIL")
    args.gh_token = args.gh_token or os.environ.get("CLANKER_GH_TOKEN")
    args.gpg_key_id = args.gpg_key_id or os.environ.get("CLANKER_GPG_KEY_ID")


def run_devcontainer(config_path: Path, repo_root: Path, claude_args: list[str]) -> None:
    """Run the devcontainer with claude."""
    os.chdir(repo_root)

    devcontainer_cmd = ["npx", "-y", "@devcontainers/cli"]
    claude_cmd = ["claude", "--dangerously-skip-permissions"] + claude_args

    exec_cmd = devcontainer_cmd + [
        "exec",
        "--workspace-folder", ".",
        "--config", str(config_path),
    ] + claude_cmd

    result = subprocess.run(exec_cmd, stderr=subprocess.DEVNULL)

    if result.returncode != 0:
        print("Starting devcontainer...")

        up_cmd = devcontainer_cmd + [
            "up",
            "--workspace-folder", ".",
            "--config", str(config_path),
        ]

        subprocess.run(up_cmd, check=True)

        # Use execvp to replace process for clean TTY passthrough
        os.execvp("npx", exec_cmd)


def main() -> None:
    """
    Main entry point - runs claude-code locally.

    Uses embedded devcontainer files from the package.
    With --build, builds from Dockerfile. Without, uses pre-built image.
    """
    parser = create_parser()
    args, claude_args = parser.parse_known_args()
    apply_env_defaults(args)

    if args.ssh_key_file and not Path(args.ssh_key_file).exists():
        print(f"Error: SSH key not found at {args.ssh_key_file}", file=sys.stderr)
        sys.exit(1)

    # Extract embedded devcontainer files to temp directory
    workspace_dir = extract_devcontainer_to_temp()
    devcontainer_dir = workspace_dir / ".devcontainer"
    source_config = devcontainer_dir / "devcontainer.json"

    # Setup runtime directory for SSH config etc
    runtime_dir = Path.home() / ".claude" / "clanker-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Load and modify config
    config = json.loads(source_config.read_text())
    config = modify_config(config, args, runtime_dir, devcontainer_dir)

    # Write modified config back to the temp devcontainer dir
    runtime_config = devcontainer_dir / "devcontainer.json"
    runtime_config.write_text(json.dumps(config, indent=2))

    run_devcontainer(runtime_config, workspace_dir, claude_args)


IMAGE_NAME = "ghcr.io/clankerbot/clanker:latest"


def pull_docker_image() -> None:
    """Pull the latest Docker image."""
    print("Pulling Docker image...")
    subprocess.run(["docker", "pull", IMAGE_NAME], check=True)


def install() -> None:
    """
    Pull the Docker image and run claude-code.

    Devcontainer files are embedded in the package, so no download needed.
    This entry point just ensures the image is pulled before running.
    """
    # Check if we need to pull (skip if --build is in args)
    if "--build" not in sys.argv:
        pull_docker_image()

    # Run main with all arguments
    main()
