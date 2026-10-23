#!/bin/sh
set -eu
compose() { docker compose -p mist-deck-e2e -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e "$@"; }
# Reset only this disposable E2E project's database volume so changed local
# credentials cannot leave a stale PostgreSQL cluster behind.
compose down -v
compose up -d db
compose run --build --rm e2e-reset
compose up --build -d api worker web
compose run --rm e2e
