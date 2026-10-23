#!/bin/sh
set -eu
docker compose --profile test run --build --rm test
docker run --rm -v "$(pwd)/apps/web:/app" -v /app/node_modules -w /app node:22-alpine sh -c 'npm ci && npm run build && npm test'
./scripts/e2e.sh
