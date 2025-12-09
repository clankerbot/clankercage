#!/bin/bash
set -e

CLAUDE_DIR="$HOME/.claude/.devcontainer"
CONFIG="$CLAUDE_DIR/devcontainer.json"
DEFAULT_SSH_KEY="$HOME/.ssh/id_ed25519_clanker"
SSH_KEY=""
GIT_USER_NAME=""
GIT_USER_EMAIL=""
GH_TOKEN=""

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
        *)
            CLAUDE_ARGS+=("$1")
            shift
            ;;
    esac
done

# Use default SSH key if not specified
if [ -z "$SSH_KEY" ]; then
    SSH_KEY="$DEFAULT_SSH_KEY"
fi

# Check for required SSH key
if [ ! -f "$SSH_KEY" ]; then
    echo "Error: SSH key not found at $SSH_KEY"
    echo "This key is required for accessing private repositories."
    echo ""
    echo "Usage: $0 [options] [claude args...]"
    echo ""
    echo "Options:"
    echo "  --ssh-key-file <path>    Path to SSH private key (default: ~/.ssh/id_ed25519_clanker)"
    echo "  --git-user-name <name>   Git user.name to configure in container"
    echo "  --git-user-email <email> Git user.email to configure in container"
    echo "  --gh-token <token>       GitHub token for gh CLI authentication"
    exit 1
fi

# Get absolute path and filename for the SSH key
SSH_KEY_PATH=$(cd "$(dirname "$SSH_KEY")" && pwd)/$(basename "$SSH_KEY")
SSH_KEY_NAME=$(basename "$SSH_KEY")

# Download devcontainer files if missing (from clankerbot/clanker repo)
if [ ! -f "$CONFIG" ]; then
    mkdir -p "$CLAUDE_DIR"
    curl -fsSL https://raw.githubusercontent.com/clankerbot/clanker/main/.devcontainer/devcontainer.json -o "$CONFIG"
    curl -fsSL https://raw.githubusercontent.com/clankerbot/clanker/main/.devcontainer/Dockerfile -o "$CLAUDE_DIR/Dockerfile"
    curl -fsSL https://raw.githubusercontent.com/clankerbot/clanker/main/.devcontainer/init-firewall.sh -o "$CLAUDE_DIR/init-firewall.sh"
    curl -fsSL https://raw.githubusercontent.com/clankerbot/clanker/main/.devcontainer/ssh_config -o "$CLAUDE_DIR/ssh_config"
fi

# Update SSH config to use the specified key name
if [ "$SSH_KEY_NAME" != "id_ed25519_clanker" ]; then
    sed -i.bak "s|id_ed25519_clanker|$SSH_KEY_NAME|g" "$CLAUDE_DIR/ssh_config"
    rm -f "$CLAUDE_DIR/ssh_config.bak"
fi

# Replace .claude docker volume with bind mount
if grep -q 'claude-code-config.*type=volume' "$CONFIG"; then
    tmp=$(mktemp)
    sed 's|source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume|source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind|' "$CONFIG" > "$tmp"
    mv "$tmp" "$CONFIG"
fi

# Add SSH key mount for private repo access
# First remove any existing SSH key mount, then add the new one
tmp=$(mktemp)
if command -v jq &>/dev/null; then
    # Remove existing SSH key mounts and add new one
    jq --arg keypath "$SSH_KEY_PATH" --arg keyname "$SSH_KEY_NAME" '
        .mounts = [.mounts[] | select(contains(".ssh/") | not)] |
        .mounts += ["source=\($keypath),target=/home/node/.ssh/\($keyname),type=bind,readonly"]
    ' "$CONFIG" > "$tmp"
else
    # Fallback without jq - just add the mount if not present
    if ! grep -q "$SSH_KEY_NAME" "$CONFIG"; then
        sed '/"mounts":/,/\]/ s|\]|, "source='"$SSH_KEY_PATH"',target=/home/node/.ssh/'"$SSH_KEY_NAME"',type=bind,readonly"]|' "$CONFIG" > "$tmp"
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
