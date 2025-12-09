# Claude Code Context Management

## Overview

Automatic conversation context management using folder-based threading.

## Architecture

- **One folder = One conversation thread**
- **Auto-load** on conversation start
- **Auto-save** after significant work
- **Portable** across machines (just copy ~/.claude)

## Directory Structure

```
~/.claude/clanker/
├── records/                                  # Context storage (NOT in git)
│   ├── <folder-name>-latest.md             # Current context
│   └── <folder-name>-YYYY-MM-DD_HH-MM-SS.md # Backups
├── tests/                                    # Test suite
├── save-context.sh                           # Helper script
├── run-tests.sh                              # Test runner
├── claude-code.sh                            # Setup script
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
bash ~/.claude/clanker/claude-code.sh
```

### Manual Setup
1. Copy `~/.claude/` from existing machine (or clone this repo to `~/.claude/clanker`)
2. Run `claude-code.sh` to setup devcontainer
3. All your contexts and settings come with you

## Testing

Run automated test suite:
```bash
bash ~/.claude/clanker/run-tests.sh
```

Expected output:
```
Running Claude Code Setup Tests...

✓ Test 1: Directory Structure
✓ Test 2: Global CLAUDE.md with auto-save instructions
✓ Test 3: Mount Verification - records/ is writable
✓ Test 4: Save Context Workflow
✓ Test 5: Context File Persistence
✓ Test 6: Host-Container Sync (check host to verify)
  File created: /Users/you/.claude/clanker/records/sync-test.md
  Verify this file exists on host machine
✓ Test 7: Folder Name Detection

================================
✓ All tests passed: 7/7
```

## Troubleshooting

**Context not saving?**
- Check `~/.claude/CLAUDE.md` has auto-save instructions
- Check `~/.claude/clanker/records/` is writable

**Can't resume context?**
- Check file exists: `ls ~/.claude/clanker/records/<folder-name>-latest.md`
- Try manual load: "Read ~/.claude/clanker/records/<folder-name>-latest.md"

**Wrong folder name?**
- Context saved as basename of current directory
- Check: `basename $PWD`

**Tests failing?**
- Make sure you're running inside the Docker container for mount tests
- Check that all scripts are executable: `chmod +x ~/.claude/clanker/*.sh ~/.claude/clanker/tests/*.sh`

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
