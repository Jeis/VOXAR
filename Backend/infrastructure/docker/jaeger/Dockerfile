# Jaeger All-in-One for VOXAR Platform
# Distributed tracing backend

FROM jaegertracing/all-in-one:latest

# Environment variables for configuration
ENV SPAN_STORAGE_TYPE=badger
ENV BADGER_EPHEMERAL=false
ENV BADGER_DIRECTORY_VALUE=/badger/data
ENV BADGER_DIRECTORY_KEY=/badger/key
ENV QUERY_BASE_PATH=/jaeger

# Create storage directories
USER root
RUN mkdir -p /badger/data /badger/key && \
    chown -R 10001:0 /badger
USER 10001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:14269/health || exit 1

# Expose ports
EXPOSE 16686 14250 14268 14269 6831 6832 5778 5775