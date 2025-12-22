import asyncio
import os
import json
import structlog
import asyncpg
from kafka import KafkaConsumer
from common.schemas import CandleEvent
from datetime import datetime

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DB_DSN = os.getenv("DB_DSN", "postgres://antigravity:password123@localhost:5432/quant_trading")

async def get_db_pool():
    return await asyncpg.create_pool(DB_DSN)

async def insert_candle(pool, event: CandleEvent):
    query = """
    INSERT INTO candles_15m (time, symbol, open, high, low, close, volume, trades)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    ON CONFLICT (time, symbol) 
    DO UPDATE SET 
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        trades = EXCLUDED.trades;
    """
    async with pool.acquire() as conn:
        await conn.execute(query, 
            event.time, 
            event.symbol, 
            event.open, 
            event.high, 
            event.low, 
            event.close, 
            event.volume, 
            event.trades
        )

def create_consumer():
    return KafkaConsumer(
        "market.candles.15m",
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id="candle-builder-group"
    )

async def consume_loop(pool):
    log.info("Starting candle consumer...")
    consumer = create_consumer()
    
    # kafka-python is blocking, so we run poll in executor or just simple loop if it's main
    # For async integration with asyncpg, we might want aiokafka, but let's wrap strictly.
    # We can just iterate consumer in a non-blocking way? 
    # kafka-python iterator is blocking.
    
    # We will use small timeout to yield control to asyncio
    while True:
        # We manually poll
        msg_batch = consumer.poll(timeout_ms=100) # blocking for up to 100ms
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    data = message.value
                    event = CandleEvent(**data)
                    await insert_candle(pool, event)
                    log.info("Persisted Candle", symbol=event.symbol, time=event.time.isoformat())
                except Exception as e:
                    log.error("Error processing message", error=str(e))
        
        await asyncio.sleep(0.01)

async def main():
    pool = await get_db_pool()
    try:
        await consume_loop(pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
