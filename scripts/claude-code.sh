#!/bin/bash
set -e

CLAUDE_DIR="$HOME/.claude/.devcontainer"
CONFIG="$CLAUDE_DIR/devcontainer.json"

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

# Add SSH agent forwarding for private repo access
if ! grep -q 'SSH_AUTH_SOCK' "$CONFIG"; then
    tmp=$(mktemp)
    # Add SSH_AUTH_SOCK mount and environment variable using jq if available, otherwise sed
    if command -v jq &>/dev/null; then
        jq '.mounts += ["source=${localEnv:SSH_AUTH_SOCK},target=/ssh-agent,type=bind"] | .containerEnv.SSH_AUTH_SOCK = "/ssh-agent"' "$CONFIG" > "$tmp"
    else
        # Fallback: add mount to existing mounts array and add containerEnv
        sed '/"mounts":/,/\]/ s|\]|, "source=\${localEnv:SSH_AUTH_SOCK},target=/ssh-agent,type=bind"]|' "$CONFIG" | \
        sed 's|"mounts"|"containerEnv": { "SSH_AUTH_SOCK": "/ssh-agent" },\n\t"mounts"|' > "$tmp"
    fi
    mv "$tmp" "$CONFIG"
fi

# Run devcontainer with stdin attached
if ! npx -y @devcontainers/cli exec --workspace-folder . --config "$CONFIG" claude --dangerously-skip-permissions 2>/dev/null </dev/tty; then
    echo "Starting devcontainer..."
    npx -y @devcontainers/cli up --workspace-folder . --config "$CONFIG" \
    && npx -y @devcontainers/cli exec --workspace-folder . --config "$CONFIG" claude --dangerously-skip-permissions </dev/tty
fi
