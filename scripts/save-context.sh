#!/bin/bash
# Usage: save-context.sh <content-file>
# Saves content to records with proper naming

FOLDER_NAME=$(basename "$PWD")
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
RECORDS_DIR="$HOME/.claude/clanker/records"

mkdir -p "$RECORDS_DIR"

# Save as latest
cp "$1" "$RECORDS_DIR/${FOLDER_NAME}-latest.md"

# Save timestamped backup
cp "$1" "$RECORDS_DIR/${FOLDER_NAME}-${TIMESTAMP}.md"

echo "Context saved to:"
echo "  - $RECORDS_DIR/${FOLDER_NAME}-latest.md"
echo "  - $RECORDS_DIR/${FOLDER_NAME}-${TIMESTAMP}.md"
