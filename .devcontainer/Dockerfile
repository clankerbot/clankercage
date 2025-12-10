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
  openssh-client \
  ca-certificates \
  iputils-ping

# Install Docker CLI and git-delta
ARG DOCKER_VERSION=27.3.1
ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
  curl -fsSL "https://download.docker.com/linux/static/stable/$(uname -m)/docker-${DOCKER_VERSION}.tgz" | tar xz --strip-components=1 -C /usr/local/bin docker/docker && \
  curl -fsSL "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" -o /tmp/git-delta.deb && \
  dpkg -i /tmp/git-delta.deb && rm /tmp/git-delta.deb

# Copy firewall scripts early (rarely change, good for caching)
COPY --chmod=755 init-firewall.sh add-domain-to-firewall.sh /usr/local/bin/

# Install Claude Code globally as root (simpler, avoids permission issues)
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
  npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Rename existing UID 1000 user to 'node' for devcontainer compatibility
# The Playwright image may have 'pwuser' or 'ubuntu' user at UID 1000 depending on version
# Also set up command history, workspace, and config directories in one layer
RUN OLD_USER=$(getent passwd 1000 | cut -d: -f1) && \
  OLD_GROUP=$(getent group 1000 | cut -d: -f1) && \
  usermod -l node -d /home/node -m "$OLD_USER" && \
  groupmod -n node "$OLD_GROUP" && \
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

# Install oh-my-zsh and configure shell
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended && \
  sed -i 's/plugins=(git)/plugins=(git fzf)/' ~/.zshrc && \
  echo 'source /usr/share/doc/fzf/examples/key-bindings.zsh || true' >> ~/.zshrc && \
  echo 'source /usr/share/doc/fzf/examples/completion.zsh || true' >> ~/.zshrc && \
  echo 'export PROMPT_COMMAND="history -a" && export HISTFILE=/commandhistory/.bash_history' >> ~/.zshrc && \
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
