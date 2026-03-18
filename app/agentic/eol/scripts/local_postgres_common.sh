#!/usr/bin/env bash

POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16}"
PG_CONTAINER_NAME="${PG_CONTAINER_NAME:-eol-local-postgres}"
PG_VOLUME_NAME="${PG_VOLUME_NAME:-eol-local-postgres-data}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-eol}"
PGUSER="${PGUSER:-eol}"
PGPASSWORD="${PGPASSWORD:-eolpass}"
POSTGRES_RUNTIME=""
POSTGRES_RUNTIME_LABEL=""

find_available_port() {
    local candidate="$1"

    if ! command -v lsof >/dev/null 2>&1; then
        echo "$candidate"
        return
    fi

    while lsof -PiTCP:"$candidate" -sTCP:LISTEN -t >/dev/null 2>&1; do
        candidate=$((candidate + 1))
    done

    echo "$candidate"
}

ensure_docker_available() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker is required for local PostgreSQL but was not found on PATH."
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        echo "Docker is installed but the daemon is not reachable. Start Docker and retry."
        exit 1
    fi
}

postgres_endpoint_reachable() {
    DATABASE_URL_TO_CHECK="${DATABASE_URL:-}"
    PGHOST_TO_CHECK="$PGHOST"
    PGPORT_TO_CHECK="$PGPORT"
    python3 - <<'PY' >/dev/null 2>&1
import os
import socket
import sys
from urllib.parse import urlparse

dsn = os.environ.get("DATABASE_URL_TO_CHECK", "")
host = os.environ.get("PGHOST_TO_CHECK", "127.0.0.1")
port = int(os.environ.get("PGPORT_TO_CHECK", "5432"))

if dsn:
    parsed = urlparse(dsn)
    if parsed.hostname:
        host = parsed.hostname
    if parsed.port:
        port = parsed.port

try:
    with socket.create_connection((host, port), timeout=1.5):
        pass
except OSError:
    sys.exit(1)

sys.exit(0)
PY
}

ensure_local_postgres_container() {
    local container_exists
    local container_running

    container_exists="$(docker ps -a --filter "name=^/${PG_CONTAINER_NAME}$" --format '{{.Names}}')"
    container_running="$(docker ps --filter "name=^/${PG_CONTAINER_NAME}$" --format '{{.Names}}')"

    if [ -z "$container_exists" ]; then
        echo "Creating local PostgreSQL container..."
        docker run -d \
            --name "$PG_CONTAINER_NAME" \
            -e POSTGRES_DB="$PGDATABASE" \
            -e POSTGRES_USER="$PGUSER" \
            -e POSTGRES_PASSWORD="$PGPASSWORD" \
            -p "$PGPORT:5432" \
            -v "$PG_VOLUME_NAME:/var/lib/postgresql/data" \
            "$POSTGRES_IMAGE" >/dev/null
    elif [ -z "$container_running" ]; then
        echo "Starting existing PostgreSQL container..."
        docker start "$PG_CONTAINER_NAME" >/dev/null
    else
        echo "Using running PostgreSQL container."
    fi
}

wait_for_local_postgres() {
    echo "Waiting for PostgreSQL readiness..."
    for attempt in $(seq 1 30); do
        if docker exec "$PG_CONTAINER_NAME" pg_isready -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; then
            return 0
        fi

        if [ "$attempt" -eq 30 ]; then
            echo "PostgreSQL did not become ready in time."
            exit 1
        fi

        sleep 1
    done
}

ensure_postgres_available() {
    if postgres_endpoint_reachable; then
        POSTGRES_RUNTIME="external"
        POSTGRES_RUNTIME_LABEL="local PostgreSQL server"
        echo "Using existing local PostgreSQL server."
        return 0
    fi

    ensure_docker_available
    ensure_local_postgres_container
    wait_for_local_postgres
    POSTGRES_RUNTIME="docker"
    POSTGRES_RUNTIME_LABEL="local PostgreSQL container"
}

export_local_postgres_env() {
    export PGHOST
    export PGPORT
    export PGDATABASE
    export PGUSER
    export PGPASSWORD
    if [ -z "${DATABASE_URL:-}" ]; then
        export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
    fi
}
