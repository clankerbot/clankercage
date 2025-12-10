# Use Playwright base image which includes Node.js 20, Chromium, and all browser dependencies
FROM mcr.microsoft.com/playwright:v1.57.0-noble

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install basic development tools and iptables/ipset
# Note: Playwright image is Ubuntu-based, so we use apt-get
RUN apt-get update && apt-get install -y --no-install-recommends \
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
  ca-certificates \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Docker CLI only (not full Docker engine) - much faster than get.docker.com
ARG DOCKER_VERSION=27.3.1
RUN ARCH=$(dpkg --print-architecture) && \
  curl -fsSL "https://download.docker.com/linux/static/stable/$(uname -m)/docker-${DOCKER_VERSION}.tgz" | \
  tar xz --strip-components=1 -C /usr/local/bin docker/docker

# Install git-delta
ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
  wget -q "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Copy firewall scripts early (rarely change, good for caching)
COPY init-firewall.sh add-domain-to-firewall.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-firewall.sh /usr/local/bin/add-domain-to-firewall.sh

# Install Claude Code globally as root (simpler, avoids permission issues)
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Create non-root user 'node' (Playwright image uses 'pwuser', we create 'node' for compatibility)
RUN useradd -m -s /bin/zsh -u 1000 node && \
  echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh, /usr/local/bin/add-domain-to-firewall.sh" > /etc/sudoers.d/node-firewall && \
  chmod 0440 /etc/sudoers.d/node-firewall && \
  usermod -aG docker node 2>/dev/null || true

# Persist bash history
RUN mkdir /commandhistory && \
  touch /commandhistory/.bash_history && \
  chown -R node /commandhistory

# Set environment variables
ENV DEVCONTAINER=true
ENV SHELL=/bin/zsh
ENV EDITOR=nano
ENV VISUAL=nano

# Create workspace and config directories
RUN mkdir -p /workspace /home/node/.claude && \
  chown -R node:node /workspace /home/node/.claude /home/node

WORKDIR /workspace

# Switch to non-root user for remaining setup
USER node

# Install zsh with oh-my-zsh
ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
  -p git \
  -p fzf \
  -a "source /usr/share/doc/fzf/examples/key-bindings.zsh || true" \
  -a "source /usr/share/doc/fzf/examples/completion.zsh || true" \
  -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  -x

# Set up SSH for GitHub access
RUN mkdir -p ~/.ssh && \
  chmod 700 ~/.ssh && \
  ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null && \
  chmod 644 ~/.ssh/known_hosts
