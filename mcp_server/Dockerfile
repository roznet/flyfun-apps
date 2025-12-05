# Dockerfile for Euro AIP MCP Server
FROM python:3.13-slim

# Create non-root user with UID 2001
RUN groupadd -r -g 2001 flyfun-mcp && \
    useradd -r -u 2001 -g flyfun-mcp -d /app -s /bin/bash flyfun-mcp

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY shared/ /app/shared/
COPY mcp_server/ /app/mcp_server/

# Install euro_aip from GitHub (latest version)
RUN pip install "git+https://github.com/roznet/rzflight@main#egg=euro_aip&subdirectory=euro_aip"

# Create directories for logs and data with correct ownership
RUN mkdir -p /app/data /app/out /app/logs && \
    chown -R flyfun-mcp:flyfun-mcp /app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER flyfun-mcp

# Health check (MCP servers typically use stdio, but we can check process)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python.*main.py" || exit 1

# Run the MCP server
WORKDIR /app/mcp_server
CMD ["python", "main.py", "--transport", "http", "--host", "127.0.0.1", "--port", "8001"]

