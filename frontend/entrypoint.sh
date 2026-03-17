#!/bin/sh
# Replace the backend URL placeholder in nginx config at runtime
# so the frontend knows where to proxy /api/ requests.
sed -i "s|BACKEND_URL_PLACEHOLDER|${BACKEND_URL:-http://localhost:8080}|g" /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
