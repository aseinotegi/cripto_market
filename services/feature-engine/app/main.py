import asyncio
import os
import json
import structlog
import pandas as pd
import numpy as np
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import CandleEvent, FeatureVectorEvent
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from datetime import datetime

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
WINDOW_SIZE = 100 # Keep last 100 candles for calculation

# State: Dict[symbol, DataFrame]
candle_buffer = {}

consumer = KafkaConsumer(
    "market.candles.15m",
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='latest',
    group_id="feature-engine-group" 
)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def calculate_features(df: pd.DataFrame) -> dict:
    # Ensure enough data
    if len(df) < 30:
        return None

    # RSI 14
    rsi = RSIIndicator(close=df['close'], window=14).rsi()
    
    # MACD (12, 26, 9)
    macd_ind = MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
    
    # Bollinger Bands (20, 2)
    bb = BollingerBands(close=df['close'], window=20, window_dev=2)
    
    # ATR 14
    atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    
    # SMAs
    sma_20 = SMAIndicator(close=df['close'], window=20).sma_indicator()
    sma_50 = SMAIndicator(close=df['close'], window=50).sma_indicator()

    # Get latest values (iloc[-1])
    features = {
        "rsi_14": float(rsi.iloc[-1]),
        "macd": float(macd_ind.macd().iloc[-1]),
        "macd_signal": float(macd_ind.macd_signal().iloc[-1]),
        "bb_upper": float(bb.bollinger_hband().iloc[-1]),
        "bb_lower": float(bb.bollinger_lband().iloc[-1]),
        "atr_14": float(atr.average_true_range().iloc[-1]),
        "sma_20": float(sma_20.iloc[-1]),
        "sma_50": float(sma_50.iloc[-1]),
        "close": float(df['close'].iloc[-1]) # Pass through price for convenience
    }
    
    # Clean NaN (e.g. if not enough data for 50 SMA)
    # simple replacement
    return {k: (v if not np.isnan(v) else 0.0) for k, v in features.items()}

async def process_loop():
    log.info("Starting feature engine...")
    
    while True:
        # Blocking poll with timeout
        msg_batch = consumer.poll(timeout_ms=100)
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    data = message.value
                    event = CandleEvent(**data)
                    symbol = event.symbol
                    
                    # Update Buffer
                    new_row = {
                        "time": event.time, 
                        "open": event.open, 
                        "high": event.high, 
                        "low": event.low, 
                        "close": event.close, 
                        "volume": event.volume
                    }
                    
                    if symbol not in candle_buffer:
                        candle_buffer[symbol] = pd.DataFrame([new_row])
                    else:
                        # Append and slice
                        df = candle_buffer[symbol]
                        # Check if duplicate time? For now, just append
                        # Optimally we should check for duplicate timestamps to update instead of append
                        # simple concat for MVP
                        updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                        if len(updated_df) > WINDOW_SIZE:
                            updated_df = updated_df.iloc[-WINDOW_SIZE:]
                        candle_buffer[symbol] = updated_df
                    
                    # Calculate Features
                    df_calc = candle_buffer[symbol]
                    features = calculate_features(df_calc)
                    
                    if features:
                        # Publish Feature Event
                        feature_event = FeatureVectorEvent(
                            symbol=symbol,
                            features=features,
                            event_time=datetime.utcnow()
                        )
                        producer.send("features.realtime", value=feature_event.model_dump(mode='json'))
                        log.info("Emitted Features", symbol=symbol)
                        
                except Exception as e:
                    log.error("Error processing candle", error=str(e))
        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(process_loop())
