# Dockerfile for Euro AIP Web Server
FROM python:3.13-slim

# Create non-root user with UID 2000
RUN groupadd -r -g 2000 flyfun && \
    useradd -r -u 2000 -g flyfun -d /app -s /bin/bash flyfun

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install euro_aip from GitHub (latest version)
RUN pip install "git+https://github.com/roznet/rzflight@main#egg=euro_aip&subdirectory=euro_aip"

# Create directories for logs and data with correct ownership
RUN mkdir -p /app/data /app/out /app/logs && \
    chown -R flyfun:flyfun /app

# Copy entrypoint script
COPY web/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER flyfun

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Use entrypoint script (builds client and runs server)
ENTRYPOINT ["/app/entrypoint.sh"]

