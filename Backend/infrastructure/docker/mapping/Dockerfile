# Enterprise 3D Mapping Processor
# COLMAP-based reconstruction with ARM64 optimization
FROM python:3.12-slim

LABEL maintainer="spatial-platform@voxar.io"
LABEL version="2.0.0"
LABEL description="VOXAR 3D Mapping - COLMAP Integration"

# Build arguments
ARG TARGETARCH

# Security: Create non-root user
RUN groupadd --gid 1000 spatial \
    && useradd --uid 1000 --gid spatial --shell /bin/bash --create-home spatial

# Install system dependencies including COLMAP
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    # COLMAP and dependencies
    colmap \
    libboost-filesystem1.83.0 \
    libopencv-dev \
    libeigen3-dev \
    libvtk9-dev \
    python3-vtk9 \
    # Build tools for some packages
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Verify COLMAP
RUN colmap --help > /dev/null 2>&1 || (echo "COLMAP installation failed" && exit 1)

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src
ENV COLMAP_EXE=/usr/bin/colmap

# Architecture-specific optimizations
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo "Optimizing for ARM64" && \
        export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2; \
    else \
        echo "Optimizing for x86_64" && \
        export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4; \
    fi

WORKDIR /app

# Copy requirements
COPY mapping_pipeline/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=spatial:spatial mapping_pipeline/src/ ./src/
COPY --chown=spatial:spatial docker/scripts/wait-for-it.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/wait-for-it.sh

# Create directories
RUN mkdir -p /app/data/temp /app/data/cache /app/logs \
    && chown -R spatial:spatial /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

USER spatial

EXPOSE 8080

# Default: HTTP server
CMD ["python", "-m", "spatial_mapping.main"]