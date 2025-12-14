# Dockerfile for Euro AIP MCP Server
# Uses base image from Dockerfile.base
FROM flyfun-base:latest AS final

# Create non-root user with UID 2001
RUN groupadd -r -g 2001 flyfun-mcp && \
    useradd -r -u 2001 -g flyfun-mcp -d /app -s /bin/bash flyfun-mcp

# Copy application-specific code
COPY mcp_server/ /app/mcp_server/
# Copy shared application code
COPY shared/ /app/shared/

# Set correct ownership
RUN chown -R flyfun-mcp:flyfun-mcp /app

# Switch to non-root user
USER flyfun-mcp

# Health check (MCP servers typically use stdio, but we can check process)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python.*main.py" || exit 1

# Run the MCP server
WORKDIR /app/mcp_server
CMD ["python", "main.py", "--transport", "http", "--host", "127.0.0.1", "--port", "8001"]

