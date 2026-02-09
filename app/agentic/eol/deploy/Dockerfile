# Multi-stage build for EOL Application without embedded Azure MCP Server
FROM mcr.microsoft.com/playwright:v1.50.0-jammy

# Prefer prebuilt wheels during pip installs to avoid compilation failures
ENV PIP_PREFER_BINARY=1

# Set environment variables for Playwright in container
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including Node.js for Azure MCP stdio
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    ca-certificates \
    gnupg \
    unzip \
    python3.11 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x (LTS) for npx @azure/mcp
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest \
    && rm -rf /var/lib/apt/lists/*

# Install Azure CLI for runtime command execution and confirm version
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && az version

WORKDIR /app

# Copy requirements from parent directory for better Docker layer caching
COPY ../requirements.txt ./

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
# Use legacy resolver to handle complex agent-framework dependencies
RUN pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt

# Create playwright directory with correct permissions before installing browsers
RUN mkdir -p /ms-playwright && chmod 755 /ms-playwright

# Install Playwright browsers and let Playwright handle system dependencies
RUN python -m playwright install-deps chromium \
    && python -m playwright install chromium \
    || (echo "⚠️ Playwright browser installation failed - application will use fallback mode" && exit 0)

# Verify Playwright installation
RUN python -c "import playwright; print('✅ Playwright imported successfully')" || echo "⚠️ Playwright import failed"

# Set additional environment variables for container optimization
ENV CONTAINER_MODE=true
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=false

# Copy application code from parent directory
COPY ../api ./api
COPY ../agents ./agents
COPY ../utils ./utils
COPY ../mcp_servers ./mcp_servers
COPY ../static ./static
COPY ../templates ./templates
COPY ../main.py ./
COPY ../*.py ./
COPY ../startup.txt ./

# Create necessary directories with proper permissions for Azure App Service
RUN mkdir -p /home/site/ms-playwright /home/site/antenv /tmp/ms-playwright /tmp/antenv || true \
    && chmod -R 755 /home/site/ms-playwright /home/site/antenv /tmp/ms-playwright /tmp/antenv || true \
    && chmod +x startup.txt || true

# Set up environment for Azure App Service compatibility
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Use the existing startup.txt script
CMD ["bash", "startup.txt"]
