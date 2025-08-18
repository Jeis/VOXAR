# Enterprise nginx with TLS and security
FROM nginx:1.25-alpine

LABEL maintainer="spatial-platform@voxar.io"
LABEL version="1.0.0"
LABEL description="VOXAR nginx - Enterprise Grade with TLS"

# Install additional packages
RUN apk add --no-cache \
    certbot \
    certbot-nginx \
    openssl \
    apache2-utils \
    curl

# Create directories
RUN mkdir -p \
    /var/www/certbot \
    /etc/nginx/ssl \
    /var/cache/nginx/static \
    /etc/nginx/conf.d

# Copy configuration
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/conf.d/ /etc/nginx/conf.d/

# Generate self-signed certificates for development
RUN openssl req -x509 -nodes -days 365 -newkey rsa:4096 \
    -keyout /etc/nginx/ssl/privkey.pem \
    -out /etc/nginx/ssl/fullchain.pem \
    -subj "/C=US/ST=State/L=City/O=VOXAR/CN=api.voxar.io" \
    && cp /etc/nginx/ssl/fullchain.pem /etc/nginx/ssl/chain.pem \
    && cp /etc/nginx/ssl/privkey.pem /etc/nginx/ssl/monitoring-privkey.pem \
    && cp /etc/nginx/ssl/fullchain.pem /etc/nginx/ssl/monitoring-fullchain.pem \
    && cp /etc/nginx/ssl/privkey.pem /etc/nginx/ssl/admin-privkey.pem \
    && cp /etc/nginx/ssl/fullchain.pem /etc/nginx/ssl/admin-fullchain.pem

# Create default htpasswd files
RUN htpasswd -cb /etc/nginx/.htpasswd admin voxar2024! \
    && htpasswd -cb /etc/nginx/.htpasswd-admin admin voxar2024!

# Copy entrypoint
COPY docker/nginx/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

EXPOSE 80 443

ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]