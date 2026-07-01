#!/bin/bash
# Install certbot and get Let's Encrypt certificate
# Usage: ./scripts/security/setup_ssl.sh your-domain.com

DOMAIN=$1
if [ -z "$DOMAIN" ]; then
  echo "Usage: ./setup_ssl.sh your-domain.com"
  exit 1
fi

apt-get update
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d $DOMAIN --non-interactive --agree-tos \
  --email admin@$DOMAIN --redirect

# Auto-renewal cron
echo "0 12 * * * root certbot renew --quiet" >> /etc/crontab
echo "SSL configured for $DOMAIN"
