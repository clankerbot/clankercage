# ClankerCage Project Status

A sandboxed devcontainer environment for running Claude Code with `--dangerously-skip-permissions`.

## What's Done

### Core Features
- **Python CLI package** - installable via `uvx`, with `clankercage` and `clankercage-remote` entry points
- **Network firewall** - iptables-based allowlist blocking all outbound traffic except whitelisted domains
- **SSH support** - `--ssh-key-file` flag mounts keys into container
- **GPG signing** - `--gpg-key-id` flag for signed commits
- **Docker socket access** - container can run docker commands
- **`--build` flag** - build from local Dockerfile instead of GHCR image
- **`--shell` flag** - run a command instead of interactive Claude Code

### Container Tools
- [x] uv support (cache issue fixed)
- [x] pnpm support (installed via corepack)
- [x] Playwright for web browsing
- [x] Docker CLI with socket mount

### CI/CD
- [x] Container build tests (`test-container.yml`)
- [x] Dockerfile hash in cache key (fixes cache busting)
- [x] Linting workflow (ShellCheck passing)

### Testing
- [x] SSH integration test using local SSH server via clankercage CLI
- [x] Firewall verification made non-fatal (warns instead of exits)
- [x] Unit tests for SSH mount warning functionality (11 tests)

### Build Optimizations
- [x] npm cache mount for Claude Code install
- [x] ssh-keyscan moved to runtime (postStartCommand) - eliminates network dependency during build
- [x] SSH mount warning when container exists without SSH mounts

## Outstanding TODOs

### Low Priority
- [ ] Automerge on CI check pass - configure GitHub branch protection
- [ ] Hadolint: review output and fix/ignore specific rules
- [ ] Combine user/directory setup RUN commands in Dockerfile
- [ ] Consider `--recreate-container` flag for mount changes
- [ ] Document container reuse limitation in README

### GitHub Auth (Manual Steps)
- [ ] Create PAT for clankerbot (scopes: repo, workflow, write:packages)
- [ ] Run `gh auth login` with clankerbot token

### Blog Post (separate repo)
- [ ] Add "Baked-In Tools" section: pnpm, uv, Playwright, Docker socket

## Known Limitations

### Container Reuse Does NOT Update Mounts
If you run clankercage without `--ssh-key-file` first, then add it later, the SSH key won't be mounted. Docker cannot add mounts to running containers.

**Workarounds:**
1. Always set `CLANKERCAGE_SSH_KEY` env var from first run
2. Manually remove container if mount config needs to change:
   ```bash
   docker ps -a --filter "label=devcontainer.local_folder=/path/to/project" -q | xargs docker rm -f
   ```

## CLI Usage

```bash
# Local dev (in clankercage repo)
uvx --from /path/to/clankercage clankercage \
    --ssh-key-file ~/.ssh/id_ed25519_clanker \
    --git-user-name clankerbot \
    --git-user-email "248217931+clankerbot@users.noreply.github.com" \
    --gpg-key-id C567F8478F289CC4

# With local Dockerfile build
uvx --from /path/to/clankercage clankercage --build ...

# From GitHub
uvx --from git+https://github.com/clankerbot/clankercage clankercage-remote ...

# Run a single command
uv run clankercage --shell "ssh -T git@github.com"
```

## CLI Arguments

| Argument | Env Variable | Description |
|----------|--------------|-------------|
| `--ssh-key-file` | `CLANKERCAGE_SSH_KEY` | Path to SSH private key |
| `--git-user-name` | `CLANKERCAGE_GIT_USER_NAME` | Git user.name |
| `--git-user-email` | `CLANKERCAGE_GIT_USER_EMAIL` | Git user.email |
| `--gh-token` | `CLANKERCAGE_GH_TOKEN` | GitHub token |
| `--gpg-key-id` | `CLANKERCAGE_GPG_KEY_ID` | GPG key ID for signing |
| `--build` | - | Build from local Dockerfile |
| `--shell` | - | Run command instead of Claude Code |

## Key Files

| File | Purpose |
|------|---------|
| `src/clankercage/cli.py` | CLI entry points |
| `pyproject.toml` | Package config |
| `.devcontainer/devcontainer.json` | Devcontainer config |
| `.devcontainer/Dockerfile` | Container image |
| `.devcontainer/init-firewall.sh` | Network allowlist setup |
| `.devcontainer/whitelisted-domains.txt` | Allowed domains |
