# Docker-in-Docker Security Research

## Problem Statement

ClankerCage needs to develop itself: Claude Code running inside a container needs Docker access to test container functionality, while preventing escape to the host.

---

## How Anthropic Does It

Anthropic's [Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) uses OS-level primitives, NOT containers:

- **Linux:** Bubblewrap (user namespaces, seccomp)
- **macOS:** Seatbelt (sandbox-exec)

**Key insight:** They enforce **both** filesystem AND network isolation. "Without network isolation, a compromised agent could exfiltrate sensitive files; without filesystem isolation, it could escape the sandbox entirely."

Their [sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) is open source but doesn't address Docker-in-Docker—it's for isolating processes, not containers.

**Takeaway:** Anthropic sidesteps the Docker-in-Docker problem entirely by not giving Claude Docker access.

---

## Industry Approaches to Docker-in-Docker

### 1. Sysbox (Nestybox/Docker)

[Sysbox](https://github.com/nestybox/sysbox) is the most promising solution for secure Docker-in-Docker.

**How it works:**
- Alternative container runtime (`--runtime=sysbox-runc`)
- Uses Linux user namespaces to run dockerd without `--privileged`
- Root inside container maps to unprivileged user on host
- "Immutable mounts" prevent escaping via mount manipulation

**Security guarantees ([docs](https://github.com/nestybox/sysbox/blob/master/docs/quickstart/security.md)):**
- Containers have no namespaces in common with host
- Capabilities only apply to container-assigned resources
- Mount syscalls are trapped and vetted

**Limitation:** Requires Sysbox installed on host. Acquired by Docker in 2022, now part of Docker Desktop's "Hardened Desktop."

### 2. gVisor

[gVisor](https://gvisor.dev/) intercepts syscalls with a user-space kernel.

**Pros:** Strongest isolation, no VM overhead, [blocks container escapes](https://dev.to/rimelek/comparing-3-docker-container-runtimes-runc-gvisor-and-kata-containers-16j)
**Cons:** 50-100ms startup latency, significant I/O performance overhead, some syscall compatibility issues

### 3. Kata Containers

[Kata](https://katacontainers.io/) runs each container in a lightweight VM.

**Pros:** Hardware-level isolation via hypervisor
**Cons:** 150-300ms startup, requires nested virtualization (won't work in Docker Desktop)

### 4. Docker Socket Proxy

[Tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) filters Docker API requests.

**How it works:** HAProxy sits between container and socket, blocks dangerous endpoints.

**Limitation:** Can block API endpoints but cannot prevent dangerous *arguments* to allowed endpoints (e.g., can allow `docker run` but can't block `-v /:/host`).

---

## How CI/CD Platforms Handle This

| Platform | Approach |
|----------|----------|
| **GitHub Actions (hosted)** | Fresh VM per job, destroyed after. No persistence = no escape risk. |
| **Gitpod** | User namespaces for isolation, [similar to Sysbox](https://www.gitpod.io/blog/root-docker-and-vscode) |
| **Codespaces** | Runs in isolated Linux VM, DinD via features |
| **Coder** | [Recommends Sysbox](https://coder.com/docs/admin/templates/extending-templates/docker-in-workspaces) for Docker-in-Docker |

**Common theme:** Either use VMs (GitHub), user namespaces (Gitpod, Sysbox), or accept the risk with warnings.

---

## Security Comparison

| Method | Host Escape Prevention | Docker Functionality | Performance | Setup Complexity |
|--------|------------------------|---------------------|-------------|------------------|
| **Host socket mount** | None | Full | Best | Simple |
| **DinD + `--privileged`** | None | Full | Good | Simple |
| **Sysbox** | Strong (user namespaces) | Full | Good | Medium (install runtime) |
| **gVisor** | Strongest (syscall interception) | Partial (compatibility) | Degraded I/O | Medium |
| **Kata** | Strong (VM isolation) | Full | Slower startup | Complex (needs nested virt) |
| **Socket proxy** | Partial (API filtering) | Limited | Best | Simple |
| **Nested VM** | Strong (hypervisor) | Full | Overhead | Complex |

---

## Recommendation for ClankerCage

### Primary: Sysbox

**Why:**
1. Designed exactly for this use case (Docker-in-Docker without privilege)
2. Used by Gitpod, recommended by Coder
3. Acquired by Docker—likely to remain supported
4. No performance penalty vs regular Docker
5. Full Docker functionality (mounts work normally)

**Architecture:**
```
Host (Sysbox installed)
│
└── docker run --runtime=sysbox-runc clankercage
    │   Outer container:
    │   - No --privileged
    │   - No host socket
    │   - Runs its own dockerd
    │   - NET_ADMIN for firewall
    │
    └── Inner containers (started by inner dockerd)
        - Full Docker experience
        - Mounts from outer container's filesystem
        - Cannot reach host
```

**Implementation:**
1. Remove docker socket mount from devcontainer.json
2. Add Docker daemon to Dockerfile
3. Start dockerd in postStartCommand
4. Document Sysbox as host requirement for Docker features
5. Offer non-Docker mode for users without Sysbox

### Fallback: Accept Risk with Documentation

For users who can't install Sysbox:
- `--enable-docker` flag mounts host socket
- Clear warning about security implications
- Recommend running on disposable VM

---

## Sources

- [Anthropic: Claude Code Sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [Sysbox GitHub](https://github.com/nestybox/sysbox)
- [Sysbox Security Documentation](https://github.com/nestybox/sysbox/blob/master/docs/quickstart/security.md)
- [Coder: Docker in Workspaces](https://coder.com/docs/admin/templates/extending-templates/docker-in-workspaces)
- [Gitpod: Root, Docker and VS Code](https://www.gitpod.io/blog/root-docker-and-vscode)
- [Container Runtime Comparison](https://dev.to/rimelek/comparing-3-docker-container-runtimes-runc-gvisor-and-kata-containers-16j)
- [Tecnativa Docker Socket Proxy](https://github.com/Tecnativa/docker-socket-proxy)
- [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
