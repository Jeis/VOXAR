# Enterprise Nakama Server for VOXAR Platform
# Fixed platform architecture with wait-for-it script support

FROM --platform=linux/amd64 heroiclabs/nakama:3.17.1

# Install tools for enterprise-grade dependency management
USER root
RUN apt-get update && apt-get install -y \
    curl \
    bash \
    postgresql-client \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && ln -sf /usr/bin/nc.openbsd /usr/bin/nc

# Copy and setup enterprise dependency management scripts
COPY infrastructure/docker/scripts/wait-for-it.sh /usr/local/bin/wait-for-it.sh
COPY infrastructure/docker/scripts/wait-for-postgres.sh /usr/local/bin/wait-for-postgres.sh
RUN chmod +x /usr/local/bin/wait-for-it.sh /usr/local/bin/wait-for-postgres.sh

# Keep as root for compatibility
# USER nakama

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:7350/ || exit 1

# Expose standard Nakama ports
EXPOSE 7350 7351 7349