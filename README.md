# Clanker

A comprehensive setup and configuration wrapper for Claude Code.

## Overview

Clanker provides:
- **Easy Setup** - One-command devcontainer installation
- **Context Management** - Auto-load/save conversations across sessions
- **Global Configuration** - Shared settings and best practices
- **Testing Infrastructure** - Automated validation suite
- **Portability** - Sync your entire setup across machines
- **Helper Scripts** - Utilities for common operations

## Key Features

### 🚀 Quick Setup
```bash
bash <(curl -s https://raw.githubusercontent.com/clankerbot/clanker/main/scripts/claude-code.sh)
```

### 💾 Automatic Context Continuity
- **Folder-based threading** - Each directory = separate conversation
- **Auto-load** - Previous context loads automatically on start
- **Auto-save** - Context saved periodically without manual intervention
- **Timestamped backups** - Never lose conversation history

### 🔧 Configuration Management
- **Global instructions** in `~/.claude/CLAUDE.md`
- **Consistent environment** across all projects
- **Docker isolation** with proper permissions
- **Single bind mount** strategy (no complexity)

### ✅ Testing & Validation
- **7 automated tests** verify setup correctness
- **Host-container sync** validation
- **Mount verification** checks
- **Workflow testing** for all features

## Directory Structure

```
~/.claude/clanker/
├── scripts/                                  # Executable scripts
│   ├── claude-code.sh                       # Setup script
│   ├── save-context.sh                      # Context save helper
│   └── run-tests.sh                         # Test runner
├── tests/                                    # Test suite
├── records/                                  # Context storage (NOT in git)
│   ├── <folder-name>-latest.md             # Current context
│   └── <folder-name>-YYYY-MM-DD_HH-MM-SS.md # Backups
└── README.md                                 # This file
```

## Usage

### Starting New Conversation
```bash
cd ~/myproject/
# Start Claude Code
# - If records/myproject-latest.md exists: Auto-loads and continues
# - If not: Starts fresh
# - Auto-saves periodically to records/myproject-latest.md
```

### Transient Conversations
```bash
mkdir -p ~/transient/python-experiment/
cd ~/transient/python-experiment/
# Start Claude Code - auto-saves to records/python-experiment-latest.md
```

### Resuming Conversation
```bash
cd ~/myproject/
# Start Claude Code
# I'll automatically check for and load records/myproject-latest.md
# No need to say anything - it happens automatically!
```

## Setup on New Machine

### Quick Setup
```bash
# Clone this repo
git clone git@github.com:clankerbot/clanker.git ~/.claude/clanker

# Run the setup script
bash ~/.claude/clanker/scripts/claude-code.sh
```

### Manual Setup
1. Copy `~/.claude/` from existing machine (or clone this repo to `~/.claude/clanker`)
2. Run `scripts/claude-code.sh` to setup devcontainer
3. All your contexts and settings come with you

## Testing

Run automated test suite:
```bash
# Fast tests (run on host, ~1 second)
bash ~/.claude/clanker/scripts/run-tests.sh

# Integration test (starts container, ~30 seconds)
bash ~/.claude/clanker/scripts/test-container.sh
```

**Fast Tests** (validate host setup):
- ✓ Directory structure exists
- ✓ Global CLAUDE.md configured
- ✓ Files are writable
- ✓ Scripts work correctly

**Integration Test** (validates container):
- ✓ devcontainer.json is valid
- ✓ No obsolete mounts
- ✓ Container starts successfully
- ✓ Tests pass inside container

Run integration test **after making changes to devcontainer config** or when troubleshooting container issues.

## How It Works

### Auto-Load Context (Hooks)

Clanker uses Claude Code's **UserPromptSubmit hook** to automatically inject:
1. Global instructions from `~/.claude/CLAUDE.md`
2. Previous conversation context from `~/.claude/clanker/records/`

**Hook Configuration:**
- Location: `~/.claude/settings.json`
- Script: `~/.claude/hooks/load-context.sh`
- Runs on every user prompt submission

**To verify hook is working:**
```bash
# Check hook is registered
cat ~/.claude/settings.json

# Test hook script directly
bash ~/.claude/hooks/load-context.sh

# In Claude Code, type:
/hooks
# Should show: UserPromptSubmit hook registered

# Run with debug logging:
claude --debug
# Look for: "Running UserPromptSubmit hook..."
```

### Auto-Save Context

Auto-save is triggered by instructions in `~/.claude/CLAUDE.md` that tell Claude to:
- Save after completing significant tasks
- Save before conversation ends
- Save periodically (~30 minutes)

Claude reads these instructions via the hook and follows them.

## Troubleshooting

**Hook not loading context?**
- Verify hook is registered: `cat ~/.claude/settings.json`
- Test script directly: `bash ~/.claude/hooks/load-context.sh`
- Check script is executable: `ls -la ~/.claude/hooks/load-context.sh`
- Run with debug: `claude --debug`

**Context not saving?**
- Hook loads the auto-save instructions, but Claude must follow them
- Check context file was created: `ls ~/.claude/clanker/records/`
- Try manual save: Ask Claude to save context using the save-context.sh script

**Wrong folder name?**
- Context saved as basename of current directory
- Check: `basename $PWD`

**Tests failing?**
- Fast tests run on host - should always pass
- Integration test requires Docker
- Check that all scripts are executable: `chmod +x ~/.claude/clanker/scripts/*.sh`

## Development

### Adding New Tests
1. Create test script in `tests/` with format: `##-test-name.sh`
2. Follow existing test structure (exit 0 for pass, exit 1 for fail)
3. Make executable: `chmod +x tests/##-test-name.sh`
4. Test runner will automatically pick it up

### Updating Setup Script
1. Edit `claude-code.sh`
2. Test locally
3. Commit and push to repo
4. Update gist: `cat claude-code.sh | pbcopy` and paste to gist

## License

MIT
