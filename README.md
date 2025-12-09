# Clanker

Devcontainer setup and testing infrastructure for Claude Code.

## Overview

Clanker provides:
- **Easy Setup** - One-command devcontainer installation
- **Testing Infrastructure** - Automated validation suite
- **Helper Scripts** - Utilities for setup and testing
- **Plugin Ecosystem** - Works with scribble-pad and browser-fallback plugins

## Quick Setup

No installation needed! Run directly:

```bash
bash <(curl -s https://raw.githubusercontent.com/clankerbot/clanker/main/scripts/claude-code.sh)
```

This script:
- Downloads devcontainer configuration files
- Converts Claude Code's docker volume to bind mount
- Starts the devcontainer with proper permissions
- Makes `~/.claude` accessible from host and container

**That's it!** No repo to clone, no files to manage.

## Directory Structure

After running the setup script:

```
~/.claude/
└── .devcontainer/           # Docker configuration (downloaded by setup script)
    ├── devcontainer.json
    ├── Dockerfile
    └── init-firewall.sh
```

Clean and minimal - just the devcontainer config.

## Plugin Architecture

Clanker works with Claude Code plugins for extended functionality:

### [scribble-pad](https://github.com/thekevinscott/scribble-pad)
Context management plugin:
- `/save [name]` - Save conversation context
- `/load [name]` - Load previous conversation
- Auto-load on session start

### [browser-fallback](https://github.com/thekevinscott/browser-fallback)
Browser automation plugin:
- `/browse [url]` - Automate browser with Playwright
- Automatic WebFetch fallback hook
- Handles JavaScript-heavy sites

## Installation

### 1. Run Setup Script

```bash
bash <(curl -s https://raw.githubusercontent.com/clankerbot/clanker/main/scripts/claude-code.sh)
```

### 2. Install Plugins (Optional)

```bash
# Add plugin marketplaces
/plugin marketplace add thekevinscott/scribble-pad
/plugin marketplace add thekevinscott/browser-fallback

# Install plugins
/plugin install scribble-pad@scribble-pad
/plugin install browser-fallback@browser-fallback
```

No repos to clone - everything installs directly from GitHub!

## Testing

Run automated test suite:

```bash
# Fast tests (run on host)
bash ~/.claude/clanker/scripts/run-tests.sh

# Integration tests (starts container)
bash ~/.claude/clanker/scripts/test-container.sh

# Python tests (if installed)
cd ~/.claude/clanker
make test
```

**Fast Tests** (validate host setup):
- ✓ Directory structure exists
- ✓ Scripts are executable
- ✓ Files are writable

**Integration Test** (validates container):
- ✓ devcontainer.json is valid
- ✓ Container starts successfully
- ✓ Bind mount works correctly
- ✓ Tests pass inside container

## How It Works

### Devcontainer Setup

Clanker modifies the default Claude Code devcontainer to use a bind mount instead of a volume:

**Before:**
```json
{
  "mounts": [
    "source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume"
  ]
}
```

**After:**
```json
{
  "mounts": [
    "source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind"
  ]
}
```

This makes `~/.claude` accessible from both host and container, enabling:
- Easy plugin installation
- Portable configuration across machines
- Direct file editing from host
- No docker volume complexity

### Plugin Integration

Plugins use the Claude Code plugin system:
- Commands defined in `commands/*.md`
- Hooks defined in `hooks/hooks.json`
- Scripts in `scripts/` directory

Clanker provides the infrastructure; plugins provide the functionality.

## Setup on New Machine

```bash
# Run the setup script
bash <(curl -s https://raw.githubusercontent.com/clankerbot/clanker/main/scripts/claude-code.sh)

# Install plugins (optional)
/plugin marketplace add thekevinscott/scribble-pad
/plugin marketplace add thekevinscott/browser-fallback
/plugin install scribble-pad@scribble-pad
/plugin install browser-fallback@browser-fallback
```

Done! Copy `~/.claude/` to bring your configuration if desired.

## Troubleshooting

**SSH not working for private repos?**
- Ensure your SSH agent is running on the host: `eval "$(ssh-agent -s)"`
- Add your key: `ssh-add ~/.ssh/id_ed25519`
- Verify with: `ssh-add -l`
- The setup script automatically forwards your SSH agent to the container
- Test inside container: `ssh -T git@github.com`

**Container won't start?**
- Check Docker is running
- Try: `docker system prune` (removes old containers)
- Verify devcontainer config: `cat ~/.claude/.devcontainer/devcontainer.json`

**Want to run tests?**
- Clone the repo: `git clone https://github.com/clankerbot/clanker.git`
- Run tests: `bash clanker/scripts/run-tests.sh`

**Plugins not loading?**
- Run: `/plugin list` to see installed plugins
- Check plugin directories exist
- Verify `plugin.json` is valid JSON

## Development

### Adding New Tests

1. Create test script in `tests/` with format: `##-test-name.sh`
2. Follow existing test structure (exit 0 for pass, exit 1 for fail)
3. Make executable: `chmod +x tests/##-test-name.sh`
4. Test runner will automatically pick it up

### Updating Setup Script

1. Edit `scripts/claude-code.sh`
2. Test locally
3. Commit and push to repo

## Architecture Principles

1. **Minimal Core** - Clanker handles only devcontainer setup
2. **Plugin Ecosystem** - Extended functionality via plugins
3. **Bind Mount Strategy** - Single `~/.claude` mount for simplicity
4. **Portable Configuration** - Git-tracked setup works across machines
5. **Test-Driven** - Automated tests verify everything works

## License

MIT
