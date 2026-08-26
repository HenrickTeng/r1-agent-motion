#!/usr/bin/env bash
set -euo pipefail
out=${1:-/tmp/r1-gateway-tls}
mkdir -p "$out"
openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj '/CN=R1 Dev CA' -keyout "$out/ca-key.pem" -out "$out/teacher-ca.pem" >/dev/null 2>&1
openssl req -newkey rsa:2048 -nodes -subj '/CN=R1 Gateway' -keyout "$out/server-key.pem" -out "$out/server.csr" >/dev/null 2>&1
openssl x509 -req -days 7 -in "$out/server.csr" -CA "$out/teacher-ca.pem" -CAkey "$out/ca-key.pem" -CAcreateserial -out "$out/server-cert.pem" >/dev/null 2>&1
rm -f "$out/server.csr" "$out/teacher-ca.srl" "$out/ca-key.pem"
chmod 600 "$out/server-key.pem"
echo "$out"
