# VOXAR VPS Engine Dockerfile
# Optimized for computer vision and 3D processing

FROM python:3.11-slim-bullseye

# Install system dependencies for computer vision
RUN apt-get update && apt-get install -y \
    # Build tools
    build-essential \
    cmake \
    pkg-config \
    # OpenCV dependencies
    libopencv-dev \
    libopencv-contrib-dev \
    # Image processing libraries
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libv4l-dev \
    libxvidcore-dev \
    libx264-dev \
    # Linear algebra and optimization
    libatlas-base-dev \
    libblas-dev \
    liblapack-dev \
    libeigen3-dev \
    gfortran \
    # 3D processing
    libpcl-dev \
    # Networking and tools
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY vps_engine/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY vps_engine/ .

# Create necessary directories
RUN mkdir -p \
    /app/vps_maps \
    /app/cache \
    /app/logs \
    /app/temp

# Set permissions
RUN chmod +x main.py && \
    chown -R nobody:nogroup /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

# Switch to non-root user
USER nobody

# Expose port
EXPOSE 9000

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV OPENCV_LOG_LEVEL=ERROR

# Start the application
CMD ["python", "main.py"]