# VOXAR Cloud Anchor Service Dockerfile
# Lightweight service for persistent spatial anchors

FROM python:3.11-slim-bullseye

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Build tools
    build-essential \
    # Networking and tools
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY cloud_anchor_service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY cloud_anchor_service/ .

# Create necessary directories
RUN mkdir -p \
    /app/logs \
    /app/temp

# Set permissions
RUN chmod +x main.py && \
    chown -R nobody:nogroup /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9001/health || exit 1

# Switch to non-root user
USER nobody

# Expose port
EXPOSE 9001

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Start the application
CMD ["python", "main.py"]