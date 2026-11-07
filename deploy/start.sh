#!/bin/sh
# Container entrypoint (Fly.io and local docker run).
#  - writes the race authority keypair from the AUTHORITY_KEYPAIR_JSON secret
#  - refuses to start without a real SEED_SECRET
#  - drops root and runs the server (node src/index.ts) as the "node" user
set -eu

die() { echo "start.sh: $*" >&2; exit 1; }

# --- seed secret: race seeds are derived from it, so a default or short one makes races predictable
SEED_SECRET="${SEED_SECRET:-}"
[ -n "$SEED_SECRET" ] || die "SEED_SECRET is not set (fly secrets set SEED_SECRET=\$(openssl rand -hex 32))"
[ "$SEED_SECRET" != "local-dev-secret-change-me" ] || die "SEED_SECRET is still the dev default"
[ "${#SEED_SECRET}" -ge 16 ] || die "SEED_SECRET is shorter than 16 characters"
export SEED_SECRET

# --- authority keypair: from the secret, else an existing file at AUTHORITY_KEYPAIR
KEY_FILE=/tmp/authority.json
if [ -n "${AUTHORITY_KEYPAIR_JSON:-}" ]; then
  umask 077
  printf '%s' "$AUTHORITY_KEYPAIR_JSON" > "$KEY_FILE"
  umask 022
  node -e 'const k = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
           if (!Array.isArray(k) || k.length !== 64) process.exit(1);' "$KEY_FILE" \
    || die "AUTHORITY_KEYPAIR_JSON is not a 64-number Solana keypair array"
  export AUTHORITY_KEYPAIR="$KEY_FILE"
fi
unset AUTHORITY_KEYPAIR_JSON
[ -n "${AUTHORITY_KEYPAIR:-}" ] && [ -f "$AUTHORITY_KEYPAIR" ] \
  || die "no authority keypair: set AUTHORITY_KEYPAIR_JSON (contents of a Solana id.json)"

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"
cd /app/server

if [ "$(id -u)" = "0" ]; then
  # Fly mounts volumes owned by root: hand the data dir and the key to the app user, then drop root.
  chown -R node:node "$DATA_DIR"
  [ "$AUTHORITY_KEYPAIR" = "$KEY_FILE" ] && chown node:node "$KEY_FILE"
  export HOME=/home/node USER=node
  exec setpriv --reuid=node --regid=node --init-groups node src/index.ts
fi
exec node src/index.ts
