#!/bin/bash

# MediBot - Run Backend and Frontend Together
# Usage: ./run_frontend_and_backend.sh
# Stop:  Ctrl+C (kills both processes)

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Where the running PIDs are recorded. If this session's SSH connection drops
# before Ctrl+C can run cleanup(), the backend/frontend processes are orphaned
# and keep running (they're reparented, not killed, when the shell dies) -
# this file is what lets ./stop_frontend_and_backend.sh find and stop them
# later from a brand new terminal that never saw $BACKEND_PID/$FRONTEND_PID.
PID_FILE="$PROJECT_DIR/.medibot.pids"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}       MediBot - Starting Services      ${NC}"
echo -e "${BLUE}========================================${NC}"

# Kill process and all descendants recursively
kill_tree() {
    local pid=$1
    # Get all child PIDs
    local children=$(pgrep -P $pid 2>/dev/null)
    for child in $children; do
        kill_tree $child
    done
    kill $pid 2>/dev/null
}

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping services...${NC}"

    # Kill backend process tree
    if [ ! -z "$BACKEND_PID" ]; then
        kill_tree $BACKEND_PID
        echo -e "${RED}Backend stopped${NC}"
    fi

    # Kill frontend process tree
    if [ ! -z "$FRONTEND_PID" ]; then
        kill_tree $FRONTEND_PID
        echo -e "${RED}Frontend stopped${NC}"
    fi

    # Wait briefly for processes to terminate
    sleep 1

    rm -f "$PID_FILE"
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

# Trap Ctrl+C and call cleanup
trap cleanup SIGINT SIGTERM

# Check inotify watch limit (Linux only)
if [ -f /proc/sys/fs/inotify/max_user_watches ]; then
    WATCH_LIMIT=$(cat /proc/sys/fs/inotify/max_user_watches)
    if [ "$WATCH_LIMIT" -lt 65536 ]; then
        echo -e "${YELLOW}Warning: Low file watch limit ($WATCH_LIMIT). This may cause frontend errors.${NC}"
        echo -e "Fix with: ${GREEN}sudo sysctl fs.inotify.max_user_watches=524288${NC}"
        echo ""
    fi
fi

# Check if virtual environment exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo -e "${RED}Error: Virtual environment not found at $PROJECT_DIR/.venv${NC}"
    echo -e "Run: ${YELLOW}uv venv && source .venv/bin/activate && uv pip install -r requirements.txt${NC}"
    exit 1
fi

# Check if frontend node_modules exists
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
    echo -e "${RED}Error: Frontend dependencies not installed${NC}"
    echo -e "Run: ${YELLOW}cd frontend && npm install${NC}"
    exit 1
fi

# Start Backend
echo -e "\n${GREEN}Starting Backend (FastAPI)...${NC}"
echo -e "URL: http://localhost:8000"
echo -e "Docs: http://localhost:8000/docs"
(
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    uvicorn backend.main:app --reload --host 0.0.0.0
) &
BACKEND_PID=$!
echo -e "Backend  PID: ${YELLOW}$BACKEND_PID${NC}"

# Wait a moment for backend to start
sleep 2

# Start Frontend
echo -e "\n${GREEN}Starting Frontend (Next.js)...${NC}"
echo -e "URL: http://localhost:3000"
(
    cd "$PROJECT_DIR/frontend"
    # Load nvm in non-interactive shell (needed for npm)
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
    npm run dev -- -H 0.0.0.0
) &
FRONTEND_PID=$!
echo -e "Frontend PID: ${YELLOW}$FRONTEND_PID${NC}"

# Persist PIDs so they can be stopped later even from a different terminal -
# e.g. after an SSH disconnect, which kills this script without ever running
# cleanup() above, orphaning both process trees (reparented to init, not killed).
echo "$BACKEND_PID" > "$PID_FILE"
echo "$FRONTEND_PID" >> "$PID_FILE"

echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}Both services are running!${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Backend:  http://localhost:8000  (PID $BACKEND_PID)"
echo -e "Frontend: http://localhost:3000  (PID $FRONTEND_PID)"
echo -e "\nStop normally with ${YELLOW}Ctrl+C${NC} in this terminal."
echo -e "\n${YELLOW}If this session gets disconnected${NC} (SSH drop, closed terminal,"
echo -e "etc.), Ctrl+C never runs and these are orphaned, still bound to their"
echo -e "ports. From ANY terminal, recover with the companion script:"
echo -e "  ${YELLOW}./stop_frontend_and_backend.sh${NC}"
echo -e "\nOr do it by hand - find whatever PID is bound to each port, then kill it:"
echo -e "  ${YELLOW}kill -9 \$(ss -tlnp | grep ':8000 ' | grep -oP 'pid=\\K[0-9]+' | sort -u)${NC}   # backend"
echo -e "  ${YELLOW}kill -9 \$(ss -tlnp | grep ':3000 ' | grep -oP 'pid=\\K[0-9]+' | sort -u)${NC}   # frontend"
echo -e "(this targets whatever is actually listening on the port right now -"
echo -e " works even if you never saw this terminal's output, unlike the PID"
echo -e " numbers printed above, which only make sense in THIS session.)"
echo -e "${BLUE}========================================${NC}\n"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
