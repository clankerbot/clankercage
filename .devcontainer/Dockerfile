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

# Create non-root user 'node' (Playwright image uses 'pwuser', we create 'node' for compatibility)
ARG USERNAME=node
RUN useradd -m -s /bin/zsh ${USERNAME} && \
  echo "${USERNAME} ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh, /usr/local/bin/add-domain-to-firewall.sh" > /etc/sudoers.d/node-firewall && \
  chmod 0440 /etc/sudoers.d/node-firewall && \
  usermod -aG docker ${USERNAME} 2>/dev/null || true

# Ensure node user has access to /usr/local/share
RUN mkdir -p /usr/local/share/npm-global && \
  chown -R ${USERNAME}:${USERNAME} /usr/local/share

# Persist bash history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R ${USERNAME} /commandhistory

# Set environment variables
ENV DEVCONTAINER=true
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin
ENV SHELL=/bin/zsh
ENV EDITOR=nano
ENV VISUAL=nano

# Create workspace and config directories
RUN mkdir -p /workspace /home/${USERNAME}/.claude && \
  chown -R ${USERNAME}:${USERNAME} /workspace /home/${USERNAME}/.claude /home/${USERNAME}

WORKDIR /workspace

# Switch to non-root user for remaining setup
USER ${USERNAME}

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
RUN mkdir -p /home/${USERNAME}/.ssh && \
  chmod 700 /home/${USERNAME}/.ssh && \
  ssh-keyscan github.com >> /home/${USERNAME}/.ssh/known_hosts 2>/dev/null && \
  chmod 644 /home/${USERNAME}/.ssh/known_hosts

# Install Claude Code globally with npm cache mount for speed
# Playwright is already installed in base image, just need to ensure chromium is available
RUN --mount=type=cache,target=/tmp/.npm-cache,uid=1000,gid=1000 \
  npm install -g --cache /tmp/.npm-cache @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}
