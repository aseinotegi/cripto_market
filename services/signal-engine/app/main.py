import asyncio
import os
import json
import structlog
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import FeatureVectorEvent
from app.strategies.rsi_mean_reversion import RsiMeanReversionStrategy

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Active Strategies
STRATEGIES = [
    RsiMeanReversionStrategy()
]

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

async def process_loop():
    log.info("Starting Signal Engine...", strategies=[s.strategy_id for s in STRATEGIES])
    
    while True:
        # Blocking poll with timeout
        msg_batch = consumer.poll(timeout_ms=100)
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    data = message.value
                    event = FeatureVectorEvent(**data)
                    
                    for strategy in STRATEGIES:
                        signals = strategy.on_features(event)
                        for signal in signals:
                            log.info("Signal Generated", type=signal.signal_type, symbol=signal.symbol, strategy=strategy.strategy_id)
                            producer.send("signals", value=signal.model_dump(mode='json'))
                        
                except Exception as e:
                    log.error("Error processing features", error=str(e))
        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(process_loop())
