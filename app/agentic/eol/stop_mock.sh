#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$APP_DIR/scripts/local_postgres_common.sh"

REMOVE_LOCAL_POSTGRES="${REMOVE_LOCAL_POSTGRES:-false}"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not available on PATH. Nothing to stop."
    exit 0
fi

container_exists="$(docker ps -a --filter "name=^/${PG_CONTAINER_NAME}$" --format '{{.Names}}')"

if [ -z "$container_exists" ]; then
    echo "No local PostgreSQL container named $PG_CONTAINER_NAME was found."
    exit 0
fi

if docker ps --filter "name=^/${PG_CONTAINER_NAME}$" --format '{{.Names}}' | grep -qx "$PG_CONTAINER_NAME"; then
    echo "Stopping local PostgreSQL container $PG_CONTAINER_NAME..."
    docker stop "$PG_CONTAINER_NAME" >/dev/null
else
    echo "Local PostgreSQL container $PG_CONTAINER_NAME is already stopped."
fi

if [ "$REMOVE_LOCAL_POSTGRES" = "true" ]; then
    echo "Removing local PostgreSQL container $PG_CONTAINER_NAME..."
    docker rm -f "$PG_CONTAINER_NAME" >/dev/null

    if docker volume inspect "$PG_VOLUME_NAME" >/dev/null 2>&1; then
        echo "Removing Docker volume $PG_VOLUME_NAME..."
        docker volume rm "$PG_VOLUME_NAME" >/dev/null
    fi
fi

echo "Local PostgreSQL cleanup complete."