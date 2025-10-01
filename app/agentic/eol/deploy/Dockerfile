# Use standard Python image for better cross-platform compatibility
#FROM python:3.11-slim
FROM mcr.microsoft.com/playwright:v1.50.0-jammy

# Set environment variables for Playwright in container
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
ENV DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install minimal required system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    ca-certificates \
    # added for Playwright
    gnupg \
    unzip \
    python3.11 \
    python3-pip \
    # Essential libraries for Chromium
    # fonts-liberation \
    # libglib2.0-0 \
    # libnss3 \
    # libatk-bridge2.0-0 \
    # libdrm2 \
    # libxcomposite1 \
    # libxdamage1 \
    # libxrandr2 \
    # libgbm1 \
    # libxss1 \
    # libasound2 \
    # libgtk-3-0 \
    # libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements from parent directory for better Docker layer caching
COPY ../requirements.txt ./

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Create playwright directory with correct permissions before installing browsers
RUN mkdir -p /ms-playwright && chmod 755 /ms-playwright

# Install Playwright browsers and let Playwright handle system dependencies
# This is more reliable than manually installing system packages
RUN python -m playwright install-deps chromium \
    && python -m playwright install chromium \
    || (echo "⚠️ Playwright browser installation failed - application will use fallback mode" && exit 0)

# Verify Playwright installation and set up environment
RUN python -c "import playwright; print('✅ Playwright imported successfully')" || echo "⚠️ Playwright import failed"

# Set additional environment variables for container optimization
ENV CONTAINER_MODE=true
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=false
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Copy application code from parent directory
COPY ../agents ./agents
COPY ../utils ./utils
COPY ../static ./static
COPY ../templates ./templates
COPY ../main.py ./
COPY ../*.py ./
COPY ../startup.txt ./

# Create necessary directories with proper permissions for Azure App Service
# Azure App Service typically runs as root, so we don't need non-root user
RUN mkdir -p /home/site/ms-playwright /home/site/antenv /tmp/ms-playwright /tmp/antenv || true \
    && chmod -R 755 /home/site/ms-playwright /home/site/antenv /tmp/ms-playwright /tmp/antenv || true \
    && chmod +x startup.txt || true

# Set up environment for Azure App Service compatibility
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Use the existing startup.txt script which handles permissions gracefully
CMD ["bash", "startup.txt"]
