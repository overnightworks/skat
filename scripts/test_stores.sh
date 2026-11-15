#!/usr/bin/env bash
# Run a command against a throwaway Postgres and a throwaway Redis: scripts/test_stores.sh <command> [argument...]
#
# The command finds the servers in SKAT_TEST_POSTGRES_URL and SKAT_TEST_REDIS_URL. The containers are removed when the
# command ends, is stopped, or the caller dies. Keep each image equal to the one CI's service runs.
set -euo pipefail

POSTGRES_IMAGE='postgres:18.6-alpine3.24@sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395'
REDIS_IMAGE='redis:7.4.12-alpine@sha256:338fbfc036dc5517ac0b04d6de21521085935336e565f223406180e9d84166e2'
# The cap and its 30 s grace are the repository-wide rule; the container stops within the grace.
CAP_SECONDS=1800
GRACE_SECONDS=30
LOAD_WAIT_SECONDS=1800
READY_WAIT_SECONDS=60

if [ "$#" -eq 0 ]; then
    echo "usage: $0 <command> [argument...]" >&2
    exit 2
fi

# Re-run this script under the cap, so that the trap below also runs when the cap or the caller's death ends it.
if [ -z "${SKAT_TEST_STORES_CAPPED:-}" ]; then
    SKAT_TEST_STORES_CAPPED=1 exec setpriv --pdeathsig TERM timeout -k "${GRACE_SECONDS}" "${CAP_SECONDS}" "$0" "$@"
fi

wait_for_low_load() {
    local limit waited=0 load
    limit=$(awk -v cores="$(nproc)" 'BEGIN { print 1.5 * cores }')
    while load=$(cut -d' ' -f1 /proc/loadavg) && awk -v load="${load}" -v limit="${limit}" 'BEGIN { exit !(load > limit) }'; do
        if [ "${waited}" -ge "${LOAD_WAIT_SECONDS}" ]; then
            echo "load ${load} stayed above ${limit}" >&2
            exit 1
        fi
        sleep 10
        waited=$((waited + 10))
    done
}

wait_for_low_load

postgres_container="skat-test-postgres-$$"
redis_container="skat-test-redis-$$"
trap 'docker rm --force "${postgres_container}" "${redis_container}" >/dev/null 2>&1 || true' EXIT TERM
docker run --quiet --detach --name "${postgres_container}" \
    --env POSTGRES_HOST_AUTH_METHOD=trust \
    --publish 127.0.0.1::5432 \
    --tmpfs /var/lib/postgresql \
    "${POSTGRES_IMAGE}" >/dev/null
# Redis keeps nothing on disk, as the platform's instance does.
docker run --quiet --detach --name "${redis_container}" \
    --publish 127.0.0.1::6379 \
    "${REDIS_IMAGE}" redis-server --save '' --appendonly no >/dev/null

# The image's init server listens on its socket only and restarts; the server that stays up is the one on TCP.
for _ in $(seq "${READY_WAIT_SECONDS}"); do
    docker exec "${postgres_container}" pg_isready --host 127.0.0.1 --username postgres >/dev/null 2>&1 && break
    sleep 1
done
docker exec "${postgres_container}" pg_isready --host 127.0.0.1 --username postgres >/dev/null
for _ in $(seq "${READY_WAIT_SECONDS}"); do
    docker exec "${redis_container}" redis-cli ping >/dev/null 2>&1 && break
    sleep 1
done
docker exec "${redis_container}" redis-cli ping >/dev/null

postgres_port=$(docker port "${postgres_container}" 5432/tcp | head -n 1 | sed 's/.*://')
redis_port=$(docker port "${redis_container}" 6379/tcp | head -n 1 | sed 's/.*://')
# Run as a child, not exec'd, so that the trap above survives the command.
SKAT_TEST_POSTGRES_URL="postgresql+psycopg://postgres@127.0.0.1:${postgres_port}/postgres" \
    SKAT_TEST_REDIS_URL="redis://127.0.0.1:${redis_port}/0" "$@"
