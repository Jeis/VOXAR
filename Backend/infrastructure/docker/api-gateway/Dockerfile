# Enterprise API Gateway
# Production-ready with health checks and security
FROM python:3.12-slim

# Metadata
LABEL maintainer="spatial-platform@voxar.io"
LABEL version="2.0.0"
LABEL description="VOXAR API Gateway - Enterprise Grade"

# Security: Create non-root user
RUN groupadd --gid 1000 spatial \
    && useradd --uid 1000 --gid spatial --shell /bin/bash --create-home spatial

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY api_gateway/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=spatial:spatial api_gateway/ .
COPY --chown=spatial:spatial infrastructure/docker/scripts/wait-for-it.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/wait-for-it.sh

# Create app directories
RUN mkdir -p /app/logs \
    && chown -R spatial:spatial /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER spatial

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]