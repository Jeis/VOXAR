# Enterprise Localization Service
# AR/VR localization with SLAM and VIO
FROM python:3.11-slim

LABEL maintainer="spatial-platform@voxar.io"
LABEL version="2.1.0"
LABEL description="VOXAR Localization Service - SLAM/VIO Tracking"

# Security: Create non-root user
RUN groupadd --gid 1000 spatial \
    && useradd --uid 1000 --gid spatial --shell /bin/bash --create-home spatial

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libopencv-dev \
    libeigen3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

WORKDIR /app

# Copy requirements
COPY localization_service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=spatial:spatial localization_service/ .
COPY --chown=spatial:spatial infrastructure/docker/scripts/wait-for-it.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/wait-for-it.sh

# Create directories
RUN mkdir -p /app/logs /app/vocab \
    && chown -R spatial:spatial /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

USER spatial

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]