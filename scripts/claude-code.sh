#!/bin/bash
set -e

CLAUDE_DIR="$HOME/.claude/.devcontainer"
CONFIG="$CLAUDE_DIR/devcontainer.json"

# Create directories
mkdir -p "$HOME/.claude/commands"

# Download devcontainer files if missing
if [ ! -f "$CONFIG" ]; then
    mkdir -p "$CLAUDE_DIR"
    curl -fsSL https://raw.githubusercontent.com/anthropics/claude-code/main/.devcontainer/devcontainer.json -o "$CONFIG"
    curl -fsSL https://raw.githubusercontent.com/anthropics/claude-code/main/.devcontainer/Dockerfile -o "$CLAUDE_DIR/Dockerfile"
    curl -fsSL https://raw.githubusercontent.com/anthropics/claude-code/main/.devcontainer/init-firewall.sh -o "$CLAUDE_DIR/init-firewall.sh"
fi

# Replace .claude docker volume with bind mount
if grep -q 'claude-code-config.*type=volume' "$CONFIG"; then
    tmp=$(mktemp)
    sed 's|source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume|source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind|' "$CONFIG" > "$tmp"
    mv "$tmp" "$CONFIG"
fi

# Run devcontainer with stdin attached
if ! npx -y @devcontainers/cli exec --workspace-folder . --config "$CONFIG" claude --dangerously-skip-permissions 2>/dev/null </dev/tty; then
    echo "Starting devcontainer..."
    npx -y @devcontainers/cli up --workspace-folder . --config "$CONFIG" \
    && npx -y @devcontainers/cli exec --workspace-folder . --config "$CONFIG" claude --dangerously-skip-permissions </dev/tty
fi
