#!/bin/bash

# MediBot - Stop Backend and Frontend (recovery script)
#
# Use this when run_frontend_and_backend.sh's own Ctrl+C handler never ran -
# most commonly after an SSH disconnect. In that case the backend/frontend
# process trees are orphaned (reparented to init) rather than killed: they
# keep running, still holding ports 8000/3000 and (for the backend) the
# Qdrant lock file, with no terminal left attached to Ctrl+C them.
#
# Primary mechanism: find whatever PID is actually bound to ports 8000/3000
# right now, via `ss`, and kill that - this works from a brand new terminal
# that never saw this session's $BACKEND_PID/$FRONTEND_PID, and doesn't
# depend on the .medibot.pids file (written below) still being accurate.
#
# Usage: ./stop_frontend_and_backend.sh   (from any terminal, any session)

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$PROJECT_DIR/.medibot.pids"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Recursive kill, same as run_frontend_and_backend.sh's cleanup(). A plain
# `kill $pid` only kills the PID you name; uvicorn --reload's reloader (or
# npm's subshell wrapper around `next dev`) has already forked the real
# server as a CHILD by the time you'd go to kill it, so a non-recursive kill
# orphans exactly the process you're trying to stop.
kill_tree() {
    local pid=$1
    local children
    children=$(pgrep -P "$pid" 2>/dev/null)
    for child in $children; do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null
}

# Every PID currently bound to a given TCP port (there can be more than one -
# uvicorn --reload shows both its reloader and worker as holders of the same
# listening socket).
pids_on_port() {
    ss -tlnp 2>/dev/null | grep ":$1 " | grep -oP 'pid=\K[0-9]+' | sort -u
}

stop_port() {
    local port=$1
    local label=$2
    local pids
    pids=$(pids_on_port "$port")

    if [ -z "$pids" ]; then
        echo -e "  ${label}: nothing listening on port $port."
        return
    fi

    for pid in $pids; do
        echo -e "  ${label}: killing PID ${YELLOW}$pid${NC} (and its process tree) on port $port..."
        kill_tree "$pid"
    done
}

echo -e "${YELLOW}Stopping MediBot services...${NC}"
stop_port 8000 "Backend"
stop_port 3000 "Frontend"

sleep 1

# Belt-and-suspenders: also clean up via the PID file from the session that
# started these, in case either process re-forked under a different PID
# between the port lookup above and now (rare, but cheap to also cover).
if [ -f "$PID_FILE" ]; then
    while read -r pid; do
        [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && kill_tree "$pid"
    done < "$PID_FILE"
    rm -f "$PID_FILE"
fi

# A leftover lock here makes the next ingestion/backend start fail with
# "Collection is already accessed by another instance" even though nothing
# is actually running anymore.
if [ -f "$PROJECT_DIR/backend/qdrant_data/.lock" ]; then
    rm -f "$PROJECT_DIR/backend/qdrant_data/.lock"
    echo "Cleared stale Qdrant lock."
fi

echo
if [ -z "$(pids_on_port 8000)" ] && [ -z "$(pids_on_port 3000)" ]; then
    echo -e "${GREEN}Done - ports 8000 and 3000 are both free.${NC}"
else
    echo -e "${RED}Warning: something is still listening on 8000 and/or 3000.${NC}"
    echo "Check manually with: ss -tlnp | grep -E ':(8000|3000) '"
fi
