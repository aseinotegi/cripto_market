# Antigravity.Quant - Crypto Trading Platform

Sistema de trading automatizado de criptomonedas con arquitectura de microservicios, streaming de datos en tiempo real y paper trading integrado.

## 🚀 Descripción General

**Antigravity.Quant** es una plataforma de trading cuantitativo que:
- Obtiene datos de mercado en tiempo real de exchanges (Kraken)
- Calcula indicadores técnicos (RSI, MACD, Bollinger Bands, ATR, SMA)
- Genera señales de trading basadas en estrategias configurables
- Ejecuta operaciones simuladas (Paper Trading) con un portafolio inicial de $100 USDT
- Visualiza todo en un dashboard web en tiempo real

### Características Principales
- ⚡ **Streaming en tiempo real** via WebSocket
- 📊 **Indicadores técnicos** calculados automáticamente
- 🤖 **Estrategia RSI Mean Reversion** implementada
- 💰 **Paper Trading** con seguimiento de P&L
- 🔒 **Autenticación** para acceso al dashboard
- 📈 **Gráficos de velas** interactivos

---

## 📁 Estructura del Proyecto

```
cripto_market/
├── apps/                          # Aplicaciones Frontend
│   └── web/                       # Dashboard Next.js (Puerto 3001)
│       ├── src/
│       │   ├── app/               # Pages (Next.js App Router)
│       │   │   ├── page.tsx       # Dashboard principal
│       │   │   ├── login/         # Página de login
│       │   │   └── session/       # API de autenticación
│       │   ├── components/        # Componentes React
│       │   └── middleware.ts      # Middleware de autenticación
│       └── package.json
│
├── services/                      # Microservicios Backend (Python)
│   ├── connector-marketdata/      # Obtiene datos de Kraken
│   ├── candle-builder/            # Persiste candles en TimescaleDB
│   ├── feature-engine/            # Calcula indicadores técnicos
│   ├── signal-engine/             # Genera señales de trading
│   ├── risk-engine/               # Valida órdenes y gestiona riesgo
│   ├── execution-engine/          # Ejecuta trades (Paper Trading)
│   ├── api-gateway/               # API REST + WebSocket Hub (Puerto 8000)
│   └── backtester/                # Backtesting de estrategias
│
├── libs/                          # Librerías Compartidas
│   └── common/
│       └── common/
│           └── schemas.py         # Schemas Pydantic (Eventos)
│
├── infra/                         # Infraestructura
│   ├── postgres/
│   │   └── init.sql               # Schema de TimescaleDB
│   └── monitoring/
│       └── prometheus.yml         # Config de Prometheus
│
├── logs/                          # Logs de servicios
├── docker-compose.yml             # Infraestructura (Kafka, DB, etc.)
└── start_backend.sh               # Script de inicio de servicios
```

---

## 🏗️ Arquitectura

### Diagrama de Flujo de Datos

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Kraken API    │───▶│ connector-      │───▶│   Redpanda      │
│   (Exchange)    │    │ marketdata      │    │   (Kafka)       │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                       ┌───────────────────────────────┼───────────────────────────────┐
                       │                               │                               │
                       ▼                               ▼                               ▼
              ┌─────────────────┐           ┌─────────────────┐           ┌─────────────────┐
              │ candle-builder  │           │ feature-engine  │           │   api-gateway   │
              │ (Persiste DB)   │           │ (RSI, MACD...)  │           │   (WebSocket)   │
              └────────┬────────┘           └────────┬────────┘           └────────┬────────┘
                       │                             │                             │
                       ▼                             ▼                             ▼
              ┌─────────────────┐           ┌─────────────────┐           ┌─────────────────┐
              │  TimescaleDB    │           │  signal-engine  │           │   Frontend      │
              │  (PostgreSQL)   │           │  (Estrategias)  │           │   (Next.js)     │
              └─────────────────┘           └────────┬────────┘           └─────────────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │   risk-engine   │
                                            │ (Validación)    │
                                            └────────┬────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │execution-engine │
                                            │ (Paper Trading) │
                                            └─────────────────┘
```

### Topics de Kafka (Redpanda)

| Topic | Productor | Consumidor | Descripción |
|-------|-----------|------------|-------------|
| `market.candles.15m` | connector-marketdata | candle-builder, feature-engine, api-gateway | Velas de 15 minutos |
| `features.realtime` | feature-engine | signal-engine, execution-engine | Vectores de indicadores |
| `signals` | signal-engine | risk-engine, api-gateway | Señales de trading |
| `orders.request` | risk-engine | execution-engine | Solicitudes de órdenes |
| `orders.submitted` | execution-engine | api-gateway | Confirmación de órdenes |
| `fills` | execution-engine | api-gateway | Ejecuciones/trades |
| `portfolio.updates` | execution-engine | api-gateway | Estado del portafolio |

---

## 🐳 Servicios de Infraestructura (Docker)

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| **Redpanda** | 29092 | Message Broker (Kafka-compatible) |
| **TimescaleDB** | 5432 | Base de datos de series temporales |
| **Redis** | 6379 | Cache y sesiones |
| **MinIO** | 9000/9001 | Object Storage (backups) |
| **Prometheus** | 9090 | Métricas |
| **Grafana** | 3000 | Dashboards de monitoreo |
| **Loki** | 3100 | Agregación de logs |

---

## 🔧 Despliegue

### Prerrequisitos
- Ubuntu 22.04+ / Debian 12+
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 1. Clonar el Repositorio
```bash
git clone https://github.com/aseinotegi/Apuestas.git cripto_market
cd cripto_market
```

### 2. Configurar Entorno Virtual de Python
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # Si existe, o instalar dependencias manualmente
```

### 3. Levantar Infraestructura Docker
```bash
docker compose --profile infra up -d
```

Esto inicia: Redpanda, TimescaleDB, Redis, MinIO, Prometheus, Grafana, Loki.

### 4. Iniciar API Gateway
```bash
source .venv/bin/activate
cd services/api-gateway
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Iniciar Servicios de Backend
```bash
bash start_backend.sh
```

Este script inicia:
- connector-marketdata
- candle-builder
- feature-engine
- signal-engine
- risk-engine
- execution-engine

### 6. Iniciar Frontend
```bash
cd apps/web
npm install
npm run build
PORT=3001 npm start
```

### 7. Configurar Nginx (Producción)
```nginx
server {
    listen 443 ssl;
    server_name odds.alhonarobotics.com;

    ssl_certificate /etc/letsencrypt/live/odds.alhonarobotics.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/odds.alhonarobotics.com/privkey.pem;

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    # API Backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 📊 Estructura de Datos

### Schemas de Eventos (Pydantic)

| Schema | Descripción |
|--------|-------------|
| `CandleEvent` | Vela OHLCV con tiempo, symbol, open, high, low, close, volume |
| `FeatureVectorEvent` | Diccionario de indicadores técnicos |
| `SignalEvent` | Señal de trading (ENTRY_LONG, EXIT_LONG, etc.) |
| `OrderRequestEvent` | Solicitud de orden (buy/sell, market/limit) |
| `FillEvent` | Ejecución de trade con precio, cantidad, fee |

### Tablas de Base de Datos (TimescaleDB)

| Tabla | Descripción |
|-------|-------------|
| `candles_15m` | Velas históricas (hypertable) |
| `features` | Indicadores calculados |
| `orders` | Órdenes enviadas |
| `fills` | Trades ejecutados |
| `pnl_snapshots` | Equity curve (hypertable) |
| `risk_events` | Logs de rechazos de riesgo |

---

## 🤖 Estrategia de Trading

### RSI Mean Reversion (Implementada)

**Lógica:**
- **COMPRA** cuando RSI < 30 (sobreventa)
- **VENTA** cuando RSI > 70 (sobrecompra)
- Tamaño de orden: $50 USDT por operación
- Slippage simulado: 5 bps

**Archivo:** `services/signal-engine/app/strategies/rsi_mean_reversion.py`

---

## 🛠️ Comandos Útiles

```bash
# Ver logs en tiempo real
tail -f logs/*.log

# Reiniciar todos los servicios
bash start_backend.sh

# Ver estado de contenedores
docker ps

# Conectar a la base de datos
psql postgres://antigravity:password123@localhost:5432/quant_trading

# Ver procesos Python activos
ps aux | grep python | grep -v grep
```

---

## 🔐 Autenticación

El dashboard está protegido por autenticación básica:
- **Usuario:** Configurado vía variables de entorno
- **Contraseña:** Configurada vía variables de entorno

El middleware de Next.js (`src/middleware.ts`) verifica las sesiones antes de permitir acceso al dashboard.

---

## 📈 Monitoreo

- **Grafana:** http://localhost:3000 (admin/admin)
- **Prometheus:** http://localhost:9090
- **Logs:** `logs/` directory

---

## 🚨 Notas Importantes

1. **Paper Trading:** El sistema actualmente simula trades. No está conectado a APIs de exchanges para trading real.

2. **Variables de Entorno:**
   ```bash
   export KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
   export PYTHONPATH=/path/to/cripto_market
   ```

3. **Persistencia:** Los servicios corren con `nohup`. Para producción, usar `systemd` o PM2.

---

## 📝 Licencia

Uso privado. Todos los derechos reservados.
