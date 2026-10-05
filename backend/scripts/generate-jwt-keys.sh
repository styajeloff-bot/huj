#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# generate-jwt-keys.sh — mint a fresh ES256 keypair for JWT signing.
#
# Usage:
#   ./scripts/generate-jwt-keys.sh [output-dir]
#
# Writes two files to ./keys/ (or the given dir):
#   <kid>.pem      — PKCS#8 private key (PEM)
#   <kid>.pub.pem  — SubjectPublicKeyInfo public key (PEM)
#
# The kid is date-prefixed (YYYYMMDD-<8 hex>) so the lexicographic-max rule
# in infrastructure/crypto/jwt_keys.py picks the newest key as active.
#
# -----------------------------------------------------------------------------
# Rotation workflow (rolling, zero downtime):
#   1) Run this script to mint key N+1 alongside the existing key N.
#   2) Deploy both private keys in the secret mount. jwt_keys_dir now
#      contains <oldKid>.pem + <newKid>.pem + both .pub.pem files.
#   3) FastAPI automatically picks the lexicographically-latest (= new) kid
#      as the active signer; old kid stays published in JWKS so tokens
#      still-in-flight keep validating.
#   4) After access_token_expiry_minutes + refresh_token_expiry_days have
#      passed, delete the old <kid>.pem (private) files. Leave .pub.pem
#      around one more cycle if you want auditability.
#
# -----------------------------------------------------------------------------
# Kubernetes mount example:
#
#   # Create the secret from the generated files:
#   kubectl create secret generic carcraft-jwt-keys \
#       --from-file=./keys/
#
#   # Deployment spec:
#   #   securityContext:
#   #     fsGroup: 999
#   #     fsGroupChangePolicy: OnRootMismatch
#   #   containers:
#   #     - name: fastapi
#   #       env:
#   #         - name: JWT_KEYS_DIR
#   #           value: /etc/jwt-keys
#   #       volumeMounts:
#   #         - name: jwt-keys
#   #           mountPath: /etc/jwt-keys
#   #           readOnly: true
#   #   volumes:
#   #     - name: jwt-keys
#   #       secret:
#   #         secretName: carcraft-jwt-keys
#   #         defaultMode: 0440
#   #
#   # The image runs as UID/GID 999. Keep private files group-readable only;
#   # do not weaken them to world-readable 0444/0644.
#
# -----------------------------------------------------------------------------
set -euo pipefail

OUT_DIR="${1:-./keys}"
mkdir -p "$OUT_DIR"

DATE_PART="$(date -u +%Y%m%d)"
RAND_PART="$(openssl rand -hex 4)"
KID="${DATE_PART}-${RAND_PART}"

PRIV="${OUT_DIR}/${KID}.pem"
PUB="${OUT_DIR}/${KID}.pub.pem"

# ES256 (NIST P-256 curve) private key, PKCS#8 PEM.
openssl genpkey -algorithm EC \
    -pkeyopt ec_paramgen_curve:P-256 \
    -pkeyopt ec_param_enc:named_curve \
    -out "$PRIV" >/dev/null 2>&1

openssl pkey -in "$PRIV" -pubout -out "$PUB" >/dev/null 2>&1

chmod 600 "$PRIV"
chmod 644 "$PUB"

echo "Generated ES256 keypair:"
echo "  kid:     $KID"
echo "  private: $PRIV"
echo "  public:  $PUB"
echo
echo "Set JWT_KEYS_DIR=$OUT_DIR in FastAPI to load these keys."
