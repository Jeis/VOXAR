# Localization Service - FastAPI with Computer Vision
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Create non-root user
RUN groupadd --gid 1000 spatial && \
    useradd --uid 1000 --gid spatial --shell /bin/bash --create-home spatial

# Install system dependencies for Stella VSLAM and computer vision
RUN apt-get update && apt-get install -y \
    # Build tools
    build-essential \
    cmake \
    git \
    pkg-config \
    # Core utilities
    curl \
    wget \
    # OpenCV development packages
    libopencv-dev \
    libopencv-contrib-dev \
    # OpenCV runtime dependencies (updated package names for Debian Trixie)
    libglib2.0-0 \
    libgl1-mesa-dri \
    libgthread-2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    # Additional CV libraries
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    # SLAM dependencies
    libeigen3-dev \
    libsuitesparse-dev \
    libyaml-cpp-dev \
    libgflags-dev \
    libgoogle-glog-dev \
    # g2o for graph optimization (needed by Stella VSLAM)
    libg2o-dev \
    # SQLite3 for Stella VSLAM map storage
    libsqlite3-dev \
    # Development headers
    python3-dev \
    pybind11-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Note: Stella VSLAM integration commented out due to complex build dependencies
# For development, we use the mock SLAM implementation in slam_integration.py
# To enable Stella VSLAM:
# 1. Fix g2o CMake configuration issues
# 2. Install additional dependencies (DBoW2, etc.)
# 3. Uncomment the build commands below
#
# # Build and install Stella VSLAM
# RUN git clone --recursive https://github.com/stella-cv/stella_vslam.git /tmp/stella_vslam && \
#     cd /tmp/stella_vslam && \
#     mkdir build && cd build && \
#     cmake -DCMAKE_BUILD_TYPE=Release \
#           -DBUILD_WITH_MARCH_NATIVE=OFF \
#           -DUSE_PANGOLIN_VIEWER=OFF \
#           -DUSE_SOCKET_PUBLISHER=ON \
#           -DUSE_STACK_TRACE_LOGGER=ON \
#           -DBUILD_TESTS=OFF \
#           -DBUILD_EXAMPLES=OFF .. && \
#     make -j$(nproc) && make install && \
#     cd / && rm -rf /tmp/stella_vslam

# Create placeholder for Stella VSLAM vocabulary
RUN mkdir -p /app/vocab && \
    echo "# Stella VSLAM ORB vocabulary placeholder" > /app/vocab/orb_vocab.fbow

# Install Python bindings for Stella VSLAM
RUN pip install --no-cache-dir \
    pybind11 \
    pyyaml \
    matplotlib \
    # For SLAM visualization and debugging
    pillow

# Download ORB vocabulary for Stella VSLAM
RUN mkdir -p /app/vocab && \
    wget -O /app/vocab/orb_vocab.fbow \
    https://github.com/stella-cv/FBoW_orb_vocab/raw/main/orb_vocab.fbow

# Copy application code
COPY --chown=spatial:spatial . .

# Create maps directory with proper permissions
RUN mkdir -p /app/maps && \
    chown -R spatial:spatial /app/maps && \
    chmod 755 /app/maps

# Switch to non-root user
USER spatial

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]