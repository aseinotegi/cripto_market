import asyncio
import os
import json
import structlog
import pandas as pd
import numpy as np
import asyncpg
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import CandleEvent, FeatureVectorEvent
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from datetime import datetime

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DB_DSN = os.getenv("DB_DSN", "postgres://antigravity:password123@localhost:5432/quant_trading")
WINDOW_SIZE = 100 # Keep last 100 candles for calculation
SYMBOLS = ["BTC/USDT", "ETH/USDT"]

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

async def load_historical_candles():
    """Load last WINDOW_SIZE candles from DB for each symbol."""
    log.info("Loading historical candles from database...")
    try:
        conn = await asyncpg.connect(DB_DSN)
        for symbol in SYMBOLS:
            rows = await conn.fetch(
                """
                SELECT time, open, high, low, close, volume 
                FROM candles_15m 
                WHERE symbol = $1 
                ORDER BY time DESC 
                LIMIT $2
                """,
                symbol, WINDOW_SIZE
            )
            if rows:
                df = pd.DataFrame([dict(r) for r in rows])
                df = df.sort_values('time').reset_index(drop=True)
                candle_buffer[symbol] = df
                log.info("Loaded historical candles", symbol=symbol, count=len(df))
        await conn.close()
    except Exception as e:
        log.error("Failed to load historical candles", error=str(e))

def calculate_features(df: pd.DataFrame) -> dict:
    """Calculate technical indicators for regime detection and trading signals."""
    # Minimum data for basic indicators
    if len(df) < 15:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
    
    # --- Momentum Indicators ---
    rsi = RSIIndicator(close=close, window=14).rsi()
    
    # MACD (12, 26, 9) - needs 26+ candles for full accuracy
    macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    
    # --- Trend Indicators ---
    ema_20 = EMAIndicator(close=close, window=20).ema_indicator()
    ema_50 = EMAIndicator(close=close, window=50).ema_indicator()
    sma_20 = SMAIndicator(close=close, window=20).sma_indicator()
    sma_50 = SMAIndicator(close=close, window=50).sma_indicator()
    
    # ADX 14 - needs enough data, use try/except
    try:
        adx = ADXIndicator(high=high, low=low, close=close, window=14)
        adx_value = float(adx.adx().iloc[-1])
        adx_pos_value = float(adx.adx_pos().iloc[-1])
        adx_neg_value = float(adx.adx_neg().iloc[-1])
    except (IndexError, Exception):
        # Not enough data for ADX, use defaults
        adx_value = 0.0
        adx_pos_value = 0.0
        adx_neg_value = 0.0
    
    # --- Volatility Indicators ---
    bb = BollingerBands(close=close, window=20, window_dev=2)
    atr = AverageTrueRange(high=high, low=low, close=close, window=14)
    
    # --- Donchian Channel 20 (without look-ahead) ---
    if len(df) >= 21:
        donchian_high_20 = float(high.iloc[-21:-1].max())
        donchian_low_20 = float(low.iloc[-21:-1].min())
    else:
        donchian_high_20 = float(high.iloc[:-1].max()) if len(df) > 1 else float(high.iloc[-1])
        donchian_low_20 = float(low.iloc[:-1].min()) if len(df) > 1 else float(low.iloc[-1])
    
    # ATR% - volatility as percentage of price
    atr_value = float(atr.average_true_range().iloc[-1])
    close_value = float(close.iloc[-1])
    atr_pct = (atr_value / close_value) if close_value > 0 else 0.0
    
    # Get latest values
    features = {
        # Price
        "close": close_value,
        "high": float(high.iloc[-1]),
        "low": float(low.iloc[-1]),
        
        # Momentum
        "rsi_14": float(rsi.iloc[-1]),
        "macd": float(macd_ind.macd().iloc[-1]),
        "macd_signal": float(macd_ind.macd_signal().iloc[-1]),
        
        # Trend (EMA)
        "ema_20": float(ema_20.iloc[-1]),
        "ema_50": float(ema_50.iloc[-1]),
        "sma_20": float(sma_20.iloc[-1]),
        "sma_50": float(sma_50.iloc[-1]),
        
        # Trend Strength (ADX)
        "adx_14": adx_value,
        "adx_pos": adx_pos_value,
        "adx_neg": adx_neg_value,
        
        # Volatility
        "atr_14": atr_value,
        "atr_pct": atr_pct,
        "bb_upper": float(bb.bollinger_hband().iloc[-1]),
        "bb_lower": float(bb.bollinger_lband().iloc[-1]),
        
        # Donchian (breakout levels)
        "donchian_high_20": donchian_high_20,
        "donchian_low_20": donchian_low_20,
    }
    
    # Clean NaN values
    return {k: (v if not np.isnan(v) else 0.0) for k, v in features.items()}

async def process_loop():
    log.info("Starting feature engine...")
    
    # Load historical candles from DB on startup
    await load_historical_candles()
    
    # Emit initial features for preloaded data
    for symbol, df in candle_buffer.items():
        features = calculate_features(df)
        if features:
            feature_event = FeatureVectorEvent(
                symbol=symbol,
                features=features,
                event_time=datetime.utcnow()
            )
            producer.send("features.realtime", value=feature_event.model_dump(mode='json'))
            log.info("Emitted Initial Features", symbol=symbol, rsi=features.get('rsi_14'))
    
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
