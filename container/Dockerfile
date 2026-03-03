# NanoClaw Agent Container
# Runs Claude Agent SDK in isolated Linux VM with browser automation

FROM node:22-slim

# Configure domestic apt mirrors (Debian Bookworm)
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources || \
    sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list

# Install system dependencies for Chromium and Python
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-liberation \
    fonts-noto-color-emoji \
    libgbm1 \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libcups2 \
    libdrm2 \
    libxshmfence1 \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Configure domestic pip mirror globally
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ --break-system-packages || true

# Set Chromium path for agent-browser
ENV AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Install agent-browser and claude-code globally
RUN npm install -g agent-browser @anthropic-ai/claude-code

# Install uv for MCP
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/ && \
    ln -s /usr/local/bin/uv /usr/local/bin/uvx

# Create app directory
WORKDIR /app

# Copy package files first for better caching
COPY container/agent-runner/package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY container/agent-runner/ ./

# Copy skill MCP tools (backed into image as fallback)
COPY .claude/skills/x-integration/ ./src/skills/x-integration/

# Build TypeScript
RUN npm run build

# Create workspace directories
RUN mkdir -p /workspace/group /workspace/global /workspace/extra /workspace/ipc/messages /workspace/ipc/tasks /workspace/ipc/input /home/node/.claude

# Symlink node_modules to skills dir so dynamic imports can find dependencies
RUN ln -s /app/node_modules /home/node/.claude/node_modules

# Create entrypoint script
# Optimization: Use pre-built dist instead of re-compiling at runtime
# We use --import tsx so dynamic inputs to .ts files in /home/node/.claude/skills work
RUN printf '#!/bin/bash\nset -e\ncd /app\ncat > /tmp/input.json\nnode --import tsx /app/dist/index.js < /tmp/input.json\n' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Set permissions to node user (non-root) for writable directories
# Including cache directories for npm and uv
ENV UV_CACHE_DIR=/home/node/.cache/uv
ENV npm_config_cache=/home/node/.npm
ENV NODE_PATH=/app/node_modules
RUN mkdir -p /home/node/.cache/uv /home/node/.npm && \
    chown -R node:node /workspace /home/node && \
    chmod 777 /home/node
# Switch to non-root user (required for --dangerously-skip-permissions)
# Install XHS-Downloader into the workspace
RUN git clone https://github.com/JoeanAmier/XHS-Downloader.git /workspace/group/XHS-Downloader && \
    cd /workspace/group/XHS-Downloader && \
    uv pip install --system -r requirements.txt && \
    chown -R node:node /workspace/group/XHS-Downloader

USER node

# Pre-install minimax-coding-plan-mcp for offline use
RUN uv tool install minimax-coding-plan-mcp

# Set working directory to group workspace
WORKDIR /workspace/group

# Entry point reads JSON from stdin, outputs JSON to stdout
ENTRYPOINT ["/app/entrypoint.sh"]
