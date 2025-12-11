#!/bin/bash
# Stop the Claude Code metrics stack

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping Claude Code metrics stack..."
docker compose down

echo "Done!"
