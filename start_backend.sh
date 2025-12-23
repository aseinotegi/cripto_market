#!/bin/bash

# Activar entorno virtual
source .venv/bin/activate

# Crear directorio de logs
mkdir -p logs

# Configuración de Entorno - exportar para todos los subprocesos
export KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
export PYTHONPATH=$(pwd)
export REDIS_URL="redis://localhost:6379/0"

echo "Starting Crypto Market Services..."
echo "  KAFKA: $KAFKA_BOOTSTRAP_SERVERS"
echo "  PYTHONPATH: $PYTHONPATH"
echo "  REDIS: $REDIS_URL"

# Matar procesos anteriores si existen
pkill -f "connector-marketdata" 2>/dev/null
pkill -f "feature-engine" 2>/dev/null
pkill -f "signal-engine" 2>/dev/null
pkill -f "risk-engine" 2>/dev/null
pkill -f "execution-engine" 2>/dev/null
pkill -f "candle-builder" 2>/dev/null

sleep 1

# 1. Connector Market Data
echo "Starting Connector Market Data..."
nohup python services/connector-marketdata/app/main.py > logs/connector.log 2>&1 &
echo "Connector started (PID: $!)"

# 2. Candle Builder
echo "Starting Candle Builder..."
nohup python services/candle-builder/app/main.py > logs/candle_builder.log 2>&1 &
echo "Candle Builder started (PID: $!)"

# 3. Feature Engine
echo "Starting Feature Engine..."
nohup python services/feature-engine/app/main.py > logs/feature.log 2>&1 &
echo "Feature Engine started (PID: $!)"

# 4. Signal Engine
echo "Starting Signal Engine..."
(cd services/signal-engine/app && nohup python main.py > ../../../logs/signal.log 2>&1 &)
echo "Signal Engine started"

# 5. Risk Engine
echo "Starting Risk Engine..."
nohup python services/risk-engine/app/main.py > logs/risk.log 2>&1 &
echo "Risk Engine started (PID: $!)"

# 6. Execution Engine
echo "Starting Execution Engine..."
nohup python services/execution-engine/app/main.py > logs/execution.log 2>&1 &
echo "Execution Engine started (PID: $!)"

echo ""
echo "All services started. Monitor with: tail -f logs/*.log"
