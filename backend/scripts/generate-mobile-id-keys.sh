#!/usr/bin/env sh
set -eu

# generate-mobile-id-keys.sh — mint RSA keypairs for MTS Mobile ID JWKS.
#
# Usage:
#   ./scripts/generate-mobile-id-keys.sh [JWT_KEYS_DIR]
#
# Writes four files:
#   sig.pem      — private RSA key used to sign Mobile ID request JWTs
#   sig.pub.pem  — public RSA key published as JWK use=sig
#   enc.pem      — private RSA key used to decrypt Mobile ID JWE responses
#   enc.pub.pem  — public RSA key published as JWK use=enc
#
# Existing keypairs are never overwritten. This is an operator tool; Docker
# builds never generate or embed private Mobile ID keys.

OUT_DIR="${1:-./keys}"

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"

generate_pair() {
    kid="$1"
    priv="$OUT_DIR/$kid.pem"
    pub="$OUT_DIR/$kid.pub.pem"

    if [ -f "$priv" ] && [ -f "$pub" ]; then
        echo "Mobile ID keypair already exists: $kid"
        return 0
    fi

    if [ -f "$priv" ] || [ -f "$pub" ]; then
        echo "Refusing to overwrite partial Mobile ID keypair: $kid" >&2
        echo "Remove both $priv and $pub, or restore the missing file." >&2
        return 1
    fi

    openssl genpkey \
        -algorithm RSA \
        -pkeyopt rsa_keygen_bits:2048 \
        -out "$priv" >/dev/null 2>&1
    openssl pkey -in "$priv" -pubout -out "$pub" >/dev/null 2>&1
    chmod 600 "$priv"
    chmod 644 "$pub"

    echo "Generated Mobile ID keypair: $kid"
}

generate_pair sig
generate_pair enc

echo "Set JWT_KEYS_DIR=$OUT_DIR"
echo "Set MOBILE_ID_SIG_KID=sig"
echo "Set MOBILE_ID_ENC_KID=enc"
