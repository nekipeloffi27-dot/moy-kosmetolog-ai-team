# Dev sandbox image — used by all dev agents (backend / frontend_web / frontend_mobile).
# Built locally on the VM: `docker build -t ai-team-dev-sandbox:latest agents/dev/sandbox/`
#
# This image contains:
#   - git, gh CLI (for clone + PR creation)
#   - Claude Code CLI (npm package @anthropic-ai/claude-code)
#   - Python 3.12 + Node 20 + JDK 21 (covers backend, PWA, KMP builds)
#   - Our entrypoint that takes a TASK.md and a CLAUDE.md and makes a PR

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# Core OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git build-essential \
        python3.12 python3.12-venv python3-pip \
        openjdk-21-jdk-headless \
        unzip zip jq \
    && rm -rf /var/lib/apt/lists/*

# Node 20 (for Claude Code CLI + frontend builds)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# pip baseline
RUN python3 -m pip install --break-system-packages --no-cache-dir \
    httpx ruff black pytest

# Pre-warm gradle? skip — first KMP run will fetch.

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Sandbox user (Claude Code refuses to run as root by default in some configs)
RUN useradd -m -s /bin/bash dev
USER dev
WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
