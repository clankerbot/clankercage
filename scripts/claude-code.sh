#!/bin/bash
set -e

CLAUDE_DIR="$HOME/.claude/.devcontainer"
CONFIG="$CLAUDE_DIR/devcontainer.json"
VERSION_FILE="$CLAUDE_DIR/.version"
BASE_URL="https://raw.githubusercontent.com/clankerbot/clanker/main/.devcontainer"
IMAGE_NAME="ghcr.io/clankerbot/clanker:latest"

# Initialize from environment variables (CLI args override these)
SSH_KEY="${CLANKER_SSH_KEY:-}"
GIT_USER_NAME="${CLANKER_GIT_USER_NAME:-}"
GIT_USER_EMAIL="${CLANKER_GIT_USER_EMAIL:-}"
GH_TOKEN="${CLANKER_GH_TOKEN:-}"
GPG_KEY_ID="${CLANKER_GPG_KEY_ID:-}"

# Parse arguments
CLAUDE_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --ssh-key-file)
            SSH_KEY="$2"
            shift 2
            ;;
        --ssh-key-file=*)
            SSH_KEY="${1#*=}"
            shift
            ;;
        --git-user-name)
            GIT_USER_NAME="$2"
            shift 2
            ;;
        --git-user-name=*)
            GIT_USER_NAME="${1#*=}"
            shift
            ;;
        --git-user-email)
            GIT_USER_EMAIL="$2"
            shift 2
            ;;
        --git-user-email=*)
            GIT_USER_EMAIL="${1#*=}"
            shift
            ;;
        --gh-token)
            GH_TOKEN="$2"
            shift 2
            ;;
        --gh-token=*)
            GH_TOKEN="${1#*=}"
            shift
            ;;
        --gpg-key-id)
            GPG_KEY_ID="$2"
            shift 2
            ;;
        --gpg-key-id=*)
            GPG_KEY_ID="${1#*=}"
            shift
            ;;
        *)
            CLAUDE_ARGS+=("$1")
            shift
            ;;
    esac
done

# Validate SSH key if provided
if [ -n "$SSH_KEY" ] && [ ! -f "$SSH_KEY" ]; then
    echo "Error: SSH key not found at $SSH_KEY"
    echo ""
    echo "Usage: $0 [options] [claude args...]"
    echo ""
    echo "Options:"
    echo "  --ssh-key-file <path>    Path to SSH private key (or set CLANKER_SSH_KEY)"
    echo "  --git-user-name <name>   Git user.name (or set CLANKER_GIT_USER_NAME)"
    echo "  --git-user-email <email> Git user.email (or set CLANKER_GIT_USER_EMAIL)"
    echo "  --gh-token <token>       GitHub token (or set CLANKER_GH_TOKEN)"
    echo "  --gpg-key-id <id>        GPG key ID (or set CLANKER_GPG_KEY_ID)"
    exit 1
fi

# Get absolute path and filename for the SSH key (if provided)
SSH_KEY_PATH=""
SSH_KEY_NAME=""
if [ -n "$SSH_KEY" ]; then
    SSH_KEY_PATH=$(cd "$(dirname "$SSH_KEY")" && pwd)/$(basename "$SSH_KEY")
    SSH_KEY_NAME=$(basename "$SSH_KEY")
fi

# Get latest commit SHA from GitHub API
get_remote_commit() {
    curl -fsSL "https://api.github.com/repos/clankerbot/clanker/commits/main" 2>/dev/null | grep '"sha"' | head -1 | cut -d'"' -f4
}

download_devcontainer_files() {
    mkdir -p "$CLAUDE_DIR"
    curl -fsSL "$BASE_URL/devcontainer.json" -o "$CONFIG"
}

generate_ssh_config() {
    cat > "$CLAUDE_DIR/ssh_config" << EOF
Host github.com
  HostName github.com
  User git
  IdentityFile /home/node/.ssh/$SSH_KEY_NAME
  IdentitiesOnly yes
EOF
}

# Download devcontainer files if missing or outdated
REMOTE_COMMIT=$(get_remote_commit)
LOCAL_COMMIT=""
if [ -f "$VERSION_FILE" ]; then
    LOCAL_COMMIT=$(cat "$VERSION_FILE")
fi

if [ ! -f "$CONFIG" ]; then
    echo "Downloading devcontainer files..."
    download_devcontainer_files
    echo "$REMOTE_COMMIT" > "$VERSION_FILE"
    echo "Pulling Docker image..."
    docker pull "$IMAGE_NAME"
elif [ "$REMOTE_COMMIT" != "$LOCAL_COMMIT" ]; then
    echo "New version detected (${REMOTE_COMMIT:0:7}), updating..."
    download_devcontainer_files
    echo "$REMOTE_COMMIT" > "$VERSION_FILE"

    # Pull latest image (old containers are left running)
    echo "Pulling latest Docker image..."
    docker pull "$IMAGE_NAME"
fi

# Replace .claude docker volume with bind mount
if grep -q 'claude-code-config.*type=volume' "$CONFIG"; then
    tmp=$(mktemp)
    sed 's|source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume|source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind|' "$CONFIG" > "$tmp"
    mv "$tmp" "$CONFIG"
fi

# Add SSH key, SSH config, and optionally GPG directory mounts
tmp=$(mktemp)
if command -v jq &>/dev/null; then
    # Remove existing SSH key and .gnupg mounts
    MOUNTS_FILTER='.mounts = [.mounts[] | select((contains(".ssh/") or contains(".gnupg")) | not)]'
    MOUNTS_ADD=""

    # Add SSH mounts only if SSH key is provided
    if [ -n "$SSH_KEY" ]; then
        generate_ssh_config
        SSH_CONFIG_PATH="$CLAUDE_DIR/ssh_config"
        MOUNTS_ADD=".mounts += [\"source=$SSH_KEY_PATH,target=/home/node/.ssh/$SSH_KEY_NAME,type=bind,readonly\"]"
        MOUNTS_ADD="$MOUNTS_ADD | .mounts += [\"source=$SSH_CONFIG_PATH,target=/home/node/.ssh/config,type=bind,readonly\"]"
    fi

    if [ -n "$GPG_KEY_ID" ]; then
        if [ -n "$MOUNTS_ADD" ]; then
            MOUNTS_ADD="$MOUNTS_ADD | .mounts += [\"source=\${localEnv:HOME}/.gnupg,target=/home/node/.gnupg,type=bind\"]"
        else
            MOUNTS_ADD=".mounts += [\"source=\${localEnv:HOME}/.gnupg,target=/home/node/.gnupg,type=bind\"]"
        fi
    fi

    if [ -n "$MOUNTS_ADD" ]; then
        jq "$MOUNTS_FILTER | $MOUNTS_ADD" "$CONFIG" > "$tmp"
    else
        jq "$MOUNTS_FILTER" "$CONFIG" > "$tmp"
    fi
else
    # Fallback without jq - just add SSH mounts if key provided and not present
    if [ -n "$SSH_KEY" ] && ! grep -q "$SSH_KEY_NAME" "$CONFIG"; then
        generate_ssh_config
        SSH_CONFIG_PATH="$CLAUDE_DIR/ssh_config"
        sed '/"mounts":/,/\]/ s|\]|, "source='"$SSH_KEY_PATH"',target=/home/node/.ssh/'"$SSH_KEY_NAME"',type=bind,readonly", "source='"$SSH_CONFIG_PATH"',target=/home/node/.ssh/config,type=bind,readonly"]|' "$CONFIG" > "$tmp"
    else
        cp "$CONFIG" "$tmp"
    fi
fi
mv "$tmp" "$CONFIG"

# Build the postStartCommand to configure git and gh
POST_START_COMMANDS=("sudo /usr/local/bin/init-firewall.sh")

if [ -n "$GIT_USER_NAME" ]; then
    POST_START_COMMANDS+=("git config --global user.name '$GIT_USER_NAME'")
fi

if [ -n "$GIT_USER_EMAIL" ]; then
    POST_START_COMMANDS+=("git config --global user.email '$GIT_USER_EMAIL'")
fi

if [ -n "$GPG_KEY_ID" ]; then
    POST_START_COMMANDS+=("git config --global user.signingkey '$GPG_KEY_ID'")
    POST_START_COMMANDS+=("git config --global commit.gpgsign true")
    POST_START_COMMANDS+=("git config --global gpg.program gpg")
    # Start gpg-agent - required for GPG signing in container environments
    POST_START_COMMANDS+=("gpg-connect-agent /bye >/dev/null 2>&1 || true")
fi

if [ -n "$GH_TOKEN" ]; then
    POST_START_COMMANDS+=("echo '$GH_TOKEN' | gh auth login --with-token")
fi

# Join commands with " && "
POST_START_CMD=$(printf "%s" "${POST_START_COMMANDS[0]}")
for ((i=1; i<${#POST_START_COMMANDS[@]}; i++)); do
    POST_START_CMD="$POST_START_CMD && ${POST_START_COMMANDS[$i]}"
done

# Update postStartCommand in config
if command -v jq &>/dev/null; then
    tmp=$(mktemp)
    jq --arg cmd "$POST_START_CMD" '.postStartCommand = $cmd' "$CONFIG" > "$tmp"
    mv "$tmp" "$CONFIG"
fi

# Run devcontainer with stdin attached, passing any arguments to claude
if ! npx -y @devcontainers/cli exec --workspace-folder . --config "$CONFIG" claude --dangerously-skip-permissions "${CLAUDE_ARGS[@]}" 2>/dev/null </dev/tty; then
    echo "Starting devcontainer..."
    npx -y @devcontainers/cli up --workspace-folder . --config "$CONFIG" \
    && npx -y @devcontainers/cli exec --workspace-folder . --config "$CONFIG" claude --dangerously-skip-permissions "${CLAUDE_ARGS[@]}" </dev/tty
fi
