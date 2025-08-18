# OpenTelemetry Collector for VOXAR Platform
# Enterprise-grade telemetry collection with distroless security

FROM otel/opentelemetry-collector-contrib:latest

# Copy collector configuration files
# Volume mounts will handle data directories
COPY otel-collector-config.yaml /etc/otelcol-contrib/otel-collector-config.yaml
COPY otel-collector-dev.yaml /etc/otelcol-contrib/otel-collector-dev.yaml

# Expose OTEL standard ports
EXPOSE 4317 4318 8888 8889 13133 14250

# Use default distroless entrypoint and configuration
ENTRYPOINT ["/otelcol-contrib"]
CMD ["--config=/etc/otelcol-contrib/otel-collector-config.yaml"]