#!/bin/bash

# Activar entorno virtual
source .venv/bin/activate

# Crear directorio de logs
mkdir -p logs

# Configuración de Entorno
export KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
export PYTHONPATH=$(pwd)

echo "Starting Crypto Market Services with Kafka at $KAFKA_BOOTSTRAP_SERVERS..."

# Matar procesos anteriores si existen
pkill -f "connector-marketdata" 2>/dev/null
pkill -f "feature-engine" 2>/dev/null
pkill -f "signal-engine" 2>/dev/null
pkill -f "risk-engine" 2>/dev/null
pkill -f "execution-engine" 2>/dev/null
pkill -f "candle-builder" 2>/dev/null

sleep 1

# 1. Connector Market Data (Obtiene data de Kraken/Binance)
echo "Starting Connector Market Data..."
nohup python services/connector-marketdata/app/main.py > logs/connector.log 2>&1 &
echo "Connector started (PID: $!)"

# 2. Candle Builder (Persiste en TimescaleDB)
echo "Starting Candle Builder..."
nohup python services/candle-builder/app/main.py > logs/candle_builder.log 2>&1 &
echo "Candle Builder started (PID: $!)"

# 3. Feature Engine (Calcula RSI, MACD, etc.)
echo "Starting Feature Engine..."
nohup python services/feature-engine/app/main.py > logs/feature.log 2>&1 &
echo "Feature Engine started (PID: $!)"

# 4. Signal Engine (Genera señales de trading)
# Ejecutar desde el directorio del servicio para que los imports relativos funcionen
echo "Starting Signal Engine..."
cd services/signal-engine/app && nohup python main.py > ../../../logs/signal.log 2>&1 &
echo "Signal Engine started (PID: $!)"
cd ../../..

# 5. Risk Engine (Valida y convierte señales en órdenes)
echo "Starting Risk Engine..."
nohup python services/risk-engine/app/main.py > logs/risk.log 2>&1 &
echo "Risk Engine started (PID: $!)"

# 6. Execution Engine (Paper Trading)
echo "Starting Execution Engine..."
nohup python services/execution-engine/app/main.py > logs/execution.log 2>&1 &
echo "Execution Engine started (PID: $!)"

echo ""
echo "All services started. Monitor with: tail -f logs/*.log"
