#!/bin/bash
# Setup GPG signing for git commits in the devcontainer
# This script configures git to use GPG signing if a key is available

set -e

# Set GPG_TTY for proper terminal handling
GPG_TTY=$(tty 2>/dev/null || echo "/dev/pts/0")
export GPG_TTY

# Fix permissions on mounted .gnupg directory if needed
if [ -d "$HOME/.gnupg" ]; then
    # Ensure proper permissions (GPG requires strict permissions)
    chmod 700 "$HOME/.gnupg" 2>/dev/null || true
    chmod 600 "$HOME/.gnupg/"* 2>/dev/null || true
    chmod 700 "$HOME/.gnupg/private-keys-v1.d" 2>/dev/null || true
fi

# Check if GPG agent is running or start it
gpgconf --launch gpg-agent 2>/dev/null || true

# Get the first available signing key
SIGNING_KEY=$(gpg --list-secret-keys --keyid-format=long 2>/dev/null | grep -E "^sec" | head -1 | awk '{print $2}' | cut -d'/' -f2)

if [ -n "$SIGNING_KEY" ]; then
    echo "Found GPG signing key: $SIGNING_KEY"

    # Configure git to use GPG signing
    git config --global user.signingkey "$SIGNING_KEY"
    git config --global commit.gpgsign true
    git config --global tag.gpgsign true
    git config --global gpg.program gpg

    echo "GPG signing configured successfully"
else
    echo "Warning: No GPG signing key found. Commits will not be signed."
    echo "To enable GPG signing:"
    echo "  1. Generate a GPG key: gpg --full-generate-key"
    echo "  2. Add the public key to your GitHub account"
    echo "  3. Restart the devcontainer"
fi

# Add GPG_TTY export to shell config for future sessions
if ! grep -q "GPG_TTY" "$HOME/.zshrc" 2>/dev/null; then
    echo 'export GPG_TTY=$(tty)' >> "$HOME/.zshrc"
fi
