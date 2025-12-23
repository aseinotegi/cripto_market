#!/bin/bash
# ============================================================
# Crypto Market Services Manager
# Usage: ./services.sh [start|stop|restart|status|logs]
# ============================================================

set -e

BASE_DIR="/home/ubuntu/cripto_market"
LOG_DIR="$BASE_DIR/logs"
VENV="$BASE_DIR/.venv/bin/activate"

# Environment
export KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
export PYTHONPATH="$BASE_DIR"
export REDIS_URL="redis://localhost:6379/0"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Service definitions: name:path:command
declare -A SERVICES=(
    ["connector"]="services/connector-market-data/app/main.py"
    ["candle-builder"]="services/candle-builder/app/main.py"
    ["feature-engine"]="services/feature-engine/app/main.py"
    ["signal-engine"]="services/signal-engine/app/main.py"
    ["risk-engine"]="services/risk-engine/app/main.py"
    ["execution-engine"]="services/execution-engine/app/main.py"
)

# Order matters for startup
SERVICE_ORDER=("connector" "candle-builder" "feature-engine" "signal-engine" "risk-engine" "execution-engine")

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $1"
}

get_pid() {
    local service=$1
    pgrep -f "${SERVICES[$service]}" 2>/dev/null | head -1
}

stop_service() {
    local service=$1
    local pid=$(get_pid $service)
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null
        log "Stopped $service (PID: $pid)"
    fi
}

start_service() {
    local service=$1
    local script=${SERVICES[$service]}
    
    # Check if already running
    local pid=$(get_pid $service)
    if [ -n "$pid" ]; then
        warn "$service already running (PID: $pid)"
        return
    fi
    
    cd "$BASE_DIR"
    source "$VENV"
    nohup python "$script" > "$LOG_DIR/${service}.log" 2>&1 &
    sleep 1
    
    local new_pid=$(get_pid $service)
    if [ -n "$new_pid" ]; then
        log "Started $service (PID: $new_pid)"
    else
        error "Failed to start $service"
    fi
}

start_api_gateway() {
    local pid=$(pgrep -f "uvicorn app.main" 2>/dev/null | head -1)
    if [ -n "$pid" ]; then
        warn "API Gateway already running (PID: $pid)"
        return
    fi
    
    cd "$BASE_DIR/services/api-gateway"
    source "$VENV"
    nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/api.log" 2>&1 &
    sleep 2
    log "Started API Gateway (port 8000)"
}

stop_api_gateway() {
    pkill -9 -f "uvicorn app.main" 2>/dev/null && log "Stopped API Gateway" || true
}

start_frontend() {
    local pid=$(pgrep -f "next start" 2>/dev/null | head -1)
    if [ -n "$pid" ]; then
        warn "Frontend already running (PID: $pid)"
        return
    fi
    
    cd "$BASE_DIR/apps/web"
    PORT=3001 nohup npm run start > "$LOG_DIR/frontend.log" 2>&1 &
    sleep 3
    log "Started Frontend (port 3001)"
}

stop_frontend() {
    pkill -9 -f "next start" 2>/dev/null && log "Stopped Frontend" || true
}

do_start() {
    log "Starting all services..."
    mkdir -p "$LOG_DIR"
    
    # Kill any existing processes first
    do_stop
    sleep 2
    
    # Start backend services
    for service in "${SERVICE_ORDER[@]}"; do
        start_service "$service"
    done
    
    # Start API Gateway
    start_api_gateway
    
    # Start Frontend
    start_frontend
    
    echo ""
    log "✅ All services started!"
    echo ""
    do_status
}

do_stop() {
    log "Stopping all services..."
    
    stop_frontend
    stop_api_gateway
    
    for service in "${SERVICE_ORDER[@]}"; do
        stop_service "$service"
    done
    
    log "All services stopped"
}

do_restart() {
    log "Restarting all services..."
    do_stop
    sleep 2
    do_start
}

do_status() {
    echo ""
    echo "===== SERVICE STATUS ====="
    echo ""
    
    for service in "${SERVICE_ORDER[@]}"; do
        local pid=$(get_pid $service)
        if [ -n "$pid" ]; then
            echo -e "  ${GREEN}●${NC} $service (PID: $pid)"
        else
            echo -e "  ${RED}○${NC} $service (stopped)"
        fi
    done
    
    # API Gateway
    local api_pid=$(pgrep -f "uvicorn app.main" 2>/dev/null | head -1)
    if [ -n "$api_pid" ]; then
        echo -e "  ${GREEN}●${NC} api-gateway (PID: $api_pid)"
    else
        echo -e "  ${RED}○${NC} api-gateway (stopped)"
    fi
    
    # Frontend
    local fe_pid=$(pgrep -f "next start" 2>/dev/null | head -1)
    if [ -n "$fe_pid" ]; then
        echo -e "  ${GREEN}●${NC} frontend (PID: $fe_pid)"
    else
        echo -e "  ${RED}○${NC} frontend (stopped)"
    fi
    
    echo ""
    echo "==========================="
}

do_logs() {
    local service=${2:-""}
    if [ -z "$service" ]; then
        tail -f "$LOG_DIR"/*.log
    else
        tail -f "$LOG_DIR/${service}.log"
    fi
}

# Main
case "${1:-}" in
    start)
        do_start
        ;;
    stop)
        do_stop
        ;;
    restart)
        do_restart
        ;;
    status)
        do_status
        ;;
    logs)
        do_logs "$@"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [service]}"
        echo ""
        echo "Commands:"
        echo "  start   - Start all services"
        echo "  stop    - Stop all services"
        echo "  restart - Restart all services"
        echo "  status  - Show status of all services"
        echo "  logs    - Tail logs (optionally specify service)"
        exit 1
        ;;
esac
