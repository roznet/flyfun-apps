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
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install euro_aip from git (adjust URL as needed)
# Note: This assumes euro_aip is available as a git repository
# If it's a submodule or local, adjust accordingly
RUN pip install git+https://github.com/roznet/rzflight@main#egg=euro_aip&subdirectory=euro_aip || \
    echo "Warning: euro_aip installation failed. Ensure it's available."

# Copy application code
COPY shared/ /app/shared/
COPY web/server/ /app/web/server/
COPY src/ /app/src/  # euro_aip source if needed

# Create directories for logs and data with correct ownership
RUN mkdir -p /app/data /app/out /app/cache /app/logs && \
    chown -R flyfun:flyfun /app

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

# Run the server
WORKDIR /app/web/server
CMD ["python", "main.py"]

