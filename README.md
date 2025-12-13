# ClankerCage

A sandbox for running Claude Code with full autonomy, without risking your system.

## What It Solves

You want Claude Code to run with `--dangerously-skip-permissions` so it can work without constant interruptions. But you don't want it [deleting your hard drive](https://www.tomshardware.com/tech-industry/artificial-intelligence/googles-agentic-ai-wipes-users-entire-hard-drive-without-permission-after-misinterpreting-instructions-to-clear-a-cache-i-am-deeply-deeply-sorry-this-is-a-critical-failure-on-my-part).

ClankerCage runs Claude Code inside a Docker container. The container mounts your project directory, so Claude can read and write files. But it can't touch anything else on your system. A network firewall blocks outbound traffic by default.

## Quick Start

```bash
uvx --from git+https://github.com/clankerbot/clankercage clankercage
```

## Configuration

For a dedicated GitHub identity (recommended for distinguishing AI commits from your own):

```bash
uvx --from git+https://github.com/clankerbot/clankercage clankercage \
  --ssh-key-file ~/.ssh/id_ed25519_yourbot \
  --git-user-name yourbot \
  --git-user-email "yourbot@users.noreply.github.com" \
  --gpg-key-id YOUR_GPG_KEY_ID \
  --gh-token ghp_your_github_token
```

## How It Works

- **Container isolation**: Claude runs in Docker, can only access the mounted project directory
- **Network firewall**: Outbound traffic blocked by default; whitelisted domains (npm, GitHub, PyPI, etc.) allowed
- **Git as undo**: Lean on `git reset --hard` as your escape hatch

## Forking and Customizing

This is designed to be forked. Make it your own.

**Adding dependencies**: Edit the `Dockerfile` to add tools you need. Use Claude Code to help:

```
Add playwright and ffmpeg to the Dockerfile
```

## License

MIT
