# syntax=docker/dockerfile:1
# Pit Wall: one image with the API server (Node 25, native TypeScript), the
# prebuilt web export and headless Godot for re-driving laps and races.
#
# build/web is NOT exported here: run tools/build-web.cmd before building.
# Layout mirrors the repo so the server's relative paths keep working:
#   /app/server/src             node src/index.ts
#   /app/target/idl/pitwall.json  (chain.ts: ../../target/idl/pitwall.json)
#   /app/build/web              static game (WEB_DIR)
#   /app/game                   Godot project (GAME_DIR), imported at build time
#   /opt/godot/godot            Godot 4.7.2 Linux (GODOT_BIN)

ARG NODE_IMAGE=node:25-slim

# ---------------------------------------------------------------- Godot binary
FROM ${NODE_IMAGE} AS godot
ARG GODOT_VERSION=4.7.2
# From https://github.com/godotengine/godot/releases/download/4.7.2-stable/SHA512-SUMS.txt
ARG GODOT_SHA512=9aa00f7a605200940bce3027a567b782f49bd8e940dd06ae9e987bd65aee1b1467edd56ed84fcdcbdd44354bf613bdbb4e5d2913e925850368e150c59ed54c65
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl unzip \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/godot.zip \
      "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/Godot_v${GODOT_VERSION}-stable_linux.x86_64.zip" \
 && echo "${GODOT_SHA512}  /tmp/godot.zip" | sha512sum -c - \
 && unzip -q /tmp/godot.zip -d /tmp/godot \
 && install -D -m 755 "/tmp/godot/Godot_v${GODOT_VERSION}-stable_linux.x86_64" /opt/godot/godot \
 && rm -rf /tmp/godot /tmp/godot.zip

# ---------------------------------------------------------------- server deps
FROM ${NODE_IMAGE} AS deps
# Node 25 no longer bundles corepack: install it, then it fetches the pnpm
# version pinned in package.json ("packageManager"). The image's own yarn shim
# collides with corepack's, so it goes first (this stage only).
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN rm -f /usr/local/bin/yarn /usr/local/bin/yarnpkg \
 && npm install -g corepack@latest \
 && corepack enable pnpm
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/sim/package.json packages/sim/
COPY server/package.json server/
# bufferutil / utf-8-validate (optional ws addons) ship prebuilt binaries; their
# build scripts are not approved in pnpm-workspace.yaml (allowBuilds), so skip
# them instead of failing like pnpm 11 does by default.
RUN pnpm install --frozen-lockfile --prod --config.strict-dep-builds=false

# ---------------------------------------------------------------- runtime
FROM ${NODE_IMAGE}
ENV NODE_ENV=production \
    GODOT_BIN=/opt/godot/godot \
    GAME_DIR=/app/game \
    WEB_DIR=/app/build/web \
    DATA_DIR=/data \
    PORT=8080 \
    RPC_URL=https://api.devnet.solana.com
COPY --from=godot /opt/godot /opt/godot
WORKDIR /app
COPY --from=deps /app ./
COPY packages/sim packages/sim
COPY server/src server/src
COPY target/idl/pitwall.json target/idl/pitwall.json

# Import the project once so class_name scripts resolve at re-drive time
# (.godot/global_script_class_cache.cfg) and the autoloads' fonts, sounds and
# sprites exist in .godot/imported. A second pass picks up anything the first
# pass registered late (class cache written after the scripts were parsed).
COPY game game
RUN export HOME=/tmp/godot-home \
 && (/opt/godot/godot --headless --path /app/game --import || true) \
 && /opt/godot/godot --headless --path /app/game --import \
 && test -s /app/game/.godot/global_script_class_cache.cfg \
 && rm -rf /tmp/godot-home

COPY build/web build/web
COPY brand brand
COPY --chmod=755 deploy/start.sh /usr/local/bin/pitwall-start
# Tolerate CRLF if the script was edited on Windows
RUN sed -i 's/\r$//' /usr/local/bin/pitwall-start \
 && mkdir -p /data && chown node:node /data

EXPOSE 8080
# start.sh runs as root only to fix volume ownership, then drops to "node"
CMD ["/usr/local/bin/pitwall-start"]
