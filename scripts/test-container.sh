#!/bin/bash
# Integration test: Start container and run tests inside

set -e

echo "Running Container Integration Test..."
echo ""

CLANKERCAGE_DIR="$HOME/.claude/clankercage"
CONFIG="$HOME/.claude/.devcontainer/devcontainer.json"

# Check devcontainer.json exists
if [ ! -f "$CONFIG" ]; then
    echo "✗ devcontainer.json not found at $CONFIG"
    echo "  Run scripts/claude-code.sh first to set up devcontainer"
    exit 1
fi

echo "Step 1: Validating devcontainer.json..."

# Check for invalid mounts
if grep -q 'claude/dumps' "$CONFIG"; then
    echo "✗ Found obsolete 'claude/dumps' mount in devcontainer.json"
    echo "  This mount was removed. Update your config."
    exit 1
fi

# Check for required mounts
if ! grep -q '.claude,target=/home/node/.claude' "$CONFIG"; then
    echo "✗ Missing required .claude mount in devcontainer.json"
    exit 1
fi

echo "✓ devcontainer.json validation passed"
echo ""

# Find and stop existing containers
echo "Step 2: Cleaning up existing containers..."
EXISTING=$(docker ps -a --filter "label=devcontainer.local_folder=$PWD" --format "{{.ID}}" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    echo "  Removing existing container: $EXISTING"
    docker rm -f "$EXISTING" >/dev/null 2>&1 || true
fi
echo "✓ Cleanup complete"
echo ""

# Start fresh container
echo "Step 3: Starting fresh devcontainer..."
cd "$PWD"  # Make sure we're in a valid workspace directory
if npx -y @devcontainers/cli up --workspace-folder . --config "$CONFIG" >/dev/null 2>&1; then
    echo "✓ Container started successfully"
else
    echo "✗ Failed to start container"
    echo "  Check docker logs for details"
    exit 1
fi
echo ""

# Run tests inside container
echo "Step 4: Running tests inside container..."
if npx -y @devcontainers/cli exec --workspace-folder . --config "$CONFIG" bash "$CLANKERCAGE_DIR/scripts/run-tests.sh"; then
    echo ""
    echo "================================"
    echo "✓ Container integration test passed"
    exit 0
else
    echo ""
    echo "================================"
    echo "✗ Tests failed inside container"
    exit 1
fi
