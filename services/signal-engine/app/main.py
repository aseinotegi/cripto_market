"""
Signal Engine - Detects market regime and applies appropriate strategy.
Uses RegimeDetector to classify market conditions and select strategy.
"""
import asyncio
import os
import json
import structlog
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import FeatureVectorEvent
from regime import get_regime_detector
from strategies.rsi_mean_reversion import RsiMeanReversionStrategy
from strategies.trend_following_v1 import TrendFollowingStrategy

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Strategy instances
rsi_mr_strategy = RsiMeanReversionStrategy()
trend_strategy = TrendFollowingStrategy()

# Get regime detector
regime_detector = get_regime_detector()

consumer = KafkaConsumer(
    "features.realtime",
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='latest',
    group_id="signal-engine-group" 
)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def select_strategy(regime: str):
    """Select appropriate strategy based on market regime."""
    if regime == "TREND_UP":
        return trend_strategy
    elif regime == "RANGE":
        return rsi_mr_strategy
    else:  # HIGH_VOL
        # No trading during high volatility
        return None

async def process_loop():
    log.info("Starting Signal Engine with Regime Detection...")
    
    while True:
        msg_batch = consumer.poll(timeout_ms=100)
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    data = message.value
                    event = FeatureVectorEvent(**data)
                    features = event.features
                    symbol = event.symbol
                    
                    # 1. Detect regime with hysteresis
                    regime = regime_detector.detect(features, symbol)
                    
                    # Log regime for observability
                    log.info("Regime Detected", 
                            symbol=symbol, 
                            regime=regime,
                            atr_pct=features.get('atr_pct', 0),
                            adx=features.get('adx_14', 0))
                    
                    # 2. Select strategy based on regime
                    strategy = select_strategy(regime)
                    
                    if strategy is None:
                        log.debug("No strategy active for regime", regime=regime, symbol=symbol)
                        continue
                    
                    # 3. Generate signals from selected strategy
                    signals = strategy.on_features(event, regime=regime)
                    
                    for signal in signals:
                        log.info("Signal Generated", 
                                type=signal.signal_type, 
                                symbol=signal.symbol, 
                                strategy=signal.strategy_id,
                                regime=signal.regime,
                                signal_id=signal.signal_id[:8])
                        producer.send("signals", value=signal.model_dump(mode='json'))
                        
                except Exception as e:
                    log.error("Error processing features", error=str(e))
        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(process_loop())
