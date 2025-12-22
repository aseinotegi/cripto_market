import asyncio
import os
import json
import ccxt.async_support as ccxt
import structlog
from datetime import datetime, timezone
from common.schemas import CandleEvent
from kafka import KafkaProducer

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TIMEFRAME = "15m"

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

async def poll_candles(exchange, symbol: str):
    log.info("Starting poller", symbol=symbol)
    last_candle_time = None
    
    while True:
        try:
            # Fetch last 2 candles to ensure we get the latest closed one
            ohlcv = await exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=2)
            if not ohlcv:
                await asyncio.sleep(10)
                continue

            # ohlcv format: [timestamp, open, high, low, close, volume]
            # We take the second to last one to ensure it's "closed" or the last one if we want partial
            # For this strict logic, let's take the latest completed one.
            # Usually strict quant systems wait for candle close.
            # [Previous Completed, Current In-Progress]
            
            # Let's emit the LATEST CLOSED candle. 
            # If current time is 10:05, 10:00 is technically "open" until 10:15.
            # So we want the 9:45 candle? 
            # Actually, fetch_ohlcv returns buckets based on start time.
            # If it returns [10:00, ...], that candle closes at 10:15.
            
            # For simplicity in this poller, let's assume we want to stream updates.
            # But the requirement says "avoid lookahead", so we should only emit CLOSED candles.
            
            # Implementation: Poll every 1 minute. check if we have a NEW completed candle.
            # The completed candle is the one BEFORE the last one in the list?
            # Or just check timestamp.
            
            current_time = datetime.now(timezone.utc)
            
            for candle in ohlcv:
                ts_ms = candle[0]
                dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                
                # Deduplication
                if last_candle_time and dt <= last_candle_time:
                    continue
                
                # Check if this candle is fully closed.
                # 15m candle starting at 10:00 closes at 10:15.
                # We can perform a safe check: if the NEXT candle exists, this one is closed.
                # But fetch_ohlcv(limit=2) might give [completed, in-progress].
                
                # We will emit the one at index -2 (second to last) if we have at least 2.
                # Wait, this loop iterates all.
                pass

            # Safer Logic: Always look at ohlcv[-2] (the previous one).
            if len(ohlcv) >= 2:
                closed_candle = ohlcv[-2]
                ts_ms = closed_candle[0]
                dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                
                if last_candle_time is None or dt > last_candle_time:
                    event = CandleEvent(
                        symbol=symbol,
                        time=dt,
                        open=closed_candle[1],
                        high=closed_candle[2],
                        low=closed_candle[3],
                        close=closed_candle[4],
                        volume=closed_candle[5],
                        trades=0 # CCXT often doesn't give trades in OHLCV
                    )
                    
                    producer.send("market.candles.15m", value=event.model_dump(mode='json'))
                    log.info("Emitted Candle", symbol=symbol, time=dt.isoformat())
                    last_candle_time = dt
            
            await asyncio.sleep(60) # Poll every minute

        except Exception as e:
            log.error("Polling error", error=str(e))
            await asyncio.sleep(10)

async def main():
    kraken = ccxt.kraken()
    tasks = [poll_candles(kraken, s) for s in SYMBOLS]
    await asyncio.gather(*tasks)
    await kraken.close()

if __name__ == "__main__":
    asyncio.run(main())
