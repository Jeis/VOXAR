# Grafana Loki for Log Aggregation
# Optimized for VOXAR Platform logs

FROM grafana/loki:latest

# Copy configuration
COPY loki-config.yaml /etc/loki/local-config.yaml

# Create storage directories
USER root
RUN mkdir -p /loki/data /loki/wal && \
    chown -R loki:loki /loki
USER loki

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3100/ready || exit 1

EXPOSE 3100