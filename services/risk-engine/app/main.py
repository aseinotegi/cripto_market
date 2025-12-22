import asyncio
import os
import json
import structlog
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import SignalEvent, OrderRequestEvent
from uuid import uuid4

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
MAX_POSITION_SIZE = 1000.0 # USDT

consumer = KafkaConsumer(
    "signals",
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='latest',
    group_id="risk-engine-group" 
)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

async def process_loop():
    log.info("Starting Risk Engine...")
    
    while True:
        msg_batch = consumer.poll(timeout_ms=100)
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    data = message.value
                    signal = SignalEvent(**data)
                    log.info("Received Signal", type=signal.signal_type, symbol=signal.symbol)
                    
                    # MVP Risk Logic:
                    # Trade Amount: 50 USDT (to support $100 starting balance)
                    TRADE_AMOUNT_USDT = 50.0
                    
                    # Extract price from signal reason (provided by Signal Engine)
                    price = 90000.0 # Fallback
                    if signal.reason and "close" in signal.reason:
                        price = float(signal.reason["close"])
                        
                    quantity = TRADE_AMOUNT_USDT / price
                    
                    # Round quantity to suitable precision (BTC: 5 decimals for safety)
                    quantity = round(quantity, 5)
                    
                    side = None
                    if signal.signal_type == "ENTRY_LONG":
                        side = "buy"
                    elif signal.signal_type == "EXIT_LONG":
                        side = "sell"
                    
                    if side:
                        # Emitting Order Request
                        order = OrderRequestEvent(
                            symbol=signal.symbol,
                            side=side,
                            type="market",
                            quantity=quantity
                        )
                        producer.send("orders.request", value=order.model_dump(mode='json'))
                        log.info("Approved Order", side=side, symbol=signal.symbol, quantity=quantity, price_ref=price)
                    
                except Exception as e:
                    log.error("Error processing signal", error=str(e))
        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(process_loop())
