import asyncio
import os
import json
import structlog
import asyncpg
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaConsumer
from contextlib import asynccontextmanager
from typing import List

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DB_DSN = os.getenv("DB_DSN", "postgres://antigravity:password123@localhost:5432/quant_trading")

# Global State
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db_pool
    db_pool = await asyncpg.create_pool(DB_DSN)
    log.info("DB Pool created")
    yield
    # Shutdown
    await db_pool.close()
    log.info("DB Pool closed")

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REST Endpoints ---
@app.get("/api/candles/{symbol:path}")
async def get_candles(symbol: str, limit: int = 100):
    # Unwrap URL encoding if needed, though FastAPI handles paths.
    # Symbol "BTC/USDT" comes in as "BTC/USDT" if path param.
    # We query candles_15m
    query = """
        SELECT time, open, high, low, close, volume 
        FROM candles_15m 
        WHERE symbol = $1 
        ORDER BY time DESC 
        LIMIT $2
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, symbol, limit)
    
    # Format for chart (Lightweight Charts expects time as seconds)
    return [
        {
            "time": int(r["time"].timestamp()),
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"]
        }
        for r in rows
    ][::-1] # Reverse to have ASC order for chart

# --- WebSocket Hub ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# Kafka Consumer in Backgroud
async def kafka_consumer_task():
    consumer = KafkaConsumer(
        "market.candles.15m",
        "market.trades",
        "signals",
        "orders.submitted",
        "fills",
        "portfolio.updates",
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='latest',
        group_id=None # ephemeral group for broadcasting
    )
    
    # Non-blocking poll loop wrapper
    # Using run_in_executor for the blocking consumer.poll is better,
    # but for simplicity we iterate with short timeout
    
    log.info("Starting WebSocket Gateway Consumer")
    while True:
        try:
            # Poll returns dictionary {TopicPartition: [messages]}
            # We use a short timeout to yield to event loop
            # BUT consumer.poll IS blocking. 
            # Ideally we run this in a thread.
             
            # quick hack for async loop:
            # We actually want to run the blocking poll in a separate thread and queue it back to main loop?
            # Or just use timeout_ms=100 and await sleep(0)
            
            raw_msgs = consumer.poll(timeout_ms=100)
            
            for tp, messages in raw_msgs.items():
                for message in messages:
                    # Forward to all websockets
                    # We wrap it in a standard envelope
                    envelope = {
                        "topic": message.topic,
                        "data": message.value
                    }
                    await manager.broadcast(json.dumps(envelope))
            
            await asyncio.sleep(0.01)
        except Exception as e:
            log.error("WS Consumer Error", error=str(e))
            await asyncio.sleep(1)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive / receive messages (heartbeats?)
            data = await websocket.receive_text()
            # We don't really process incoming messages yet
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Start consumer on startup
@app.on_event("startup")
async def start_consumer():
    asyncio.create_task(kafka_consumer_task())

