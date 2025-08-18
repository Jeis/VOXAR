#!/bin/sh
set -e

echo "🚀 Starting VOXAR nginx Enterprise..."

# Check for production certificates
if [ -f "/etc/letsencrypt/live/api.voxar.io/fullchain.pem" ]; then
    echo "✅ Using Let's Encrypt certificates"
    cp /etc/letsencrypt/live/api.voxar.io/fullchain.pem /etc/nginx/ssl/fullchain.pem
    cp /etc/letsencrypt/live/api.voxar.io/privkey.pem /etc/nginx/ssl/privkey.pem
    cp /etc/letsencrypt/live/api.voxar.io/chain.pem /etc/nginx/ssl/chain.pem
else
    echo "⚠️  Using self-signed certificates (development only)"
fi

# Load credentials from secrets if available
if [ -f "/run/secrets/nginx_admin_password" ]; then
    ADMIN_PASSWORD=$(cat /run/secrets/nginx_admin_password)
    htpasswd -cb /etc/nginx/.htpasswd admin "$ADMIN_PASSWORD"
    htpasswd -cb /etc/nginx/.htpasswd-admin admin "$ADMIN_PASSWORD"
    echo "✅ Loaded admin credentials from secrets"
fi

# Test nginx configuration
echo "🔧 Testing nginx configuration..."
nginx -t

# Start nginx in background for certificate renewal setup
if [ "$ENABLE_CERTBOT" = "true" ]; then
    echo "🔒 Setting up automatic certificate renewal..."
    
    # Create certbot renewal script
    cat > /etc/periodic/daily/certbot-renew << 'EOF'
#!/bin/sh
certbot renew --nginx --quiet
nginx -s reload
EOF
    chmod +x /etc/periodic/daily/certbot-renew
    
    echo "✅ Certificate auto-renewal configured"
fi

# Set up log rotation
cat > /etc/logrotate.d/nginx << 'EOF'
/var/log/nginx/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 nginx nginx
    postrotate
        if [ -f /var/run/nginx.pid ]; then
            nginx -s reopen
        fi
    endscript
}
EOF

echo "✅ nginx enterprise configuration complete"
echo "🌐 Ready to serve VOXAR platform"

# Execute the original command
exec "$@"