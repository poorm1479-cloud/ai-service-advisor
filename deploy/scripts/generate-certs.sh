#!/usr/bin/env sh
set -eu

# Generate self-signed TLS certs for local/staging HTTPS (replace with Let's Encrypt in prod).
OUT_DIR="${1:-deploy/nginx/certs}"
mkdir -p "$OUT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout "$OUT_DIR/privkey.pem" \
  -out "$OUT_DIR/fullchain.pem" \
  -subj "/CN=localhost/O=ASA/C=US" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "Wrote $OUT_DIR/fullchain.pem and privkey.pem"
