# Use Playwright base image which includes Node.js, Chromium, and all browser dependencies pre-installed
FROM mcr.microsoft.com/playwright:v1.57.0-noble

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install basic development tools and iptables/ipset
# Note: Playwright image is Ubuntu-based, so we use apt-get
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update && apt-get install -y --no-install-recommends \
  less \
  git \
  procps \
  sudo \
  fzf \
  zsh \
  man-db \
  unzip \
  gnupg2 \
  gh \
  iptables \
  ipset \
  iproute2 \
  dnsutils \
  aggregate \
  jq \
  nano \
  vim \
  openssh-client \
  wget \
  ca-certificates

# Install Docker CLI, git-delta, and cache zsh-in-docker script (parallel downloads)
ARG DOCKER_VERSION=27.3.1
ARG GIT_DELTA_VERSION=0.18.2
ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN ARCH=$(dpkg --print-architecture) && \
  curl -fsSL "https://download.docker.com/linux/static/stable/$(uname -m)/docker-${DOCKER_VERSION}.tgz" -o /tmp/docker.tgz & \
  wget -q "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" -O /tmp/git-delta.deb & \
  wget -q "https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh" -O /tmp/zsh-in-docker.sh & \
  wait && \
  tar xzf /tmp/docker.tgz --strip-components=1 -C /usr/local/bin docker/docker && \
  dpkg -i /tmp/git-delta.deb && \
  rm /tmp/docker.tgz /tmp/git-delta.deb

# Copy firewall scripts early (rarely change, good for caching)
COPY --chmod=755 init-firewall.sh add-domain-to-firewall.sh /usr/local/bin/

# Install Claude Code globally as root (simpler, avoids permission issues)
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
  npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Rename existing 'ubuntu' user (UID 1000) to 'node' for devcontainer compatibility
# The Playwright image comes with 'ubuntu' user at UID 1000, we need 'node' for our devcontainer.json
# Also set up command history, workspace, and config directories in one layer
RUN usermod -l node -d /home/node -m ubuntu && \
  groupmod -n node ubuntu && \
  chsh -s /bin/zsh node && \
  echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh, /usr/local/bin/add-domain-to-firewall.sh" > /etc/sudoers.d/node-firewall && \
  chmod 0440 /etc/sudoers.d/node-firewall && \
  (usermod -aG docker node 2>/dev/null || groupadd docker && usermod -aG docker node || true) && \
  mkdir /commandhistory && \
  touch /commandhistory/.bash_history && \
  chown -R node /commandhistory && \
  mkdir -p /workspace /home/node/.claude && \
  chown -R node:node /workspace /home/node/.claude /home/node

# Set environment variables
ENV DEVCONTAINER=true
ENV SHELL=/bin/zsh
ENV EDITOR=nano
ENV VISUAL=nano

WORKDIR /workspace

# Switch to non-root user for remaining setup
USER node

# Install zsh with oh-my-zsh (using pre-downloaded script) and set up SSH directory
RUN sh /tmp/zsh-in-docker.sh -- \
  -p git \
  -p fzf \
  -a "source /usr/share/doc/fzf/examples/key-bindings.zsh || true" \
  -a "source /usr/share/doc/fzf/examples/completion.zsh || true" \
  -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  -x && \
  rm /tmp/zsh-in-docker.sh && \
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
