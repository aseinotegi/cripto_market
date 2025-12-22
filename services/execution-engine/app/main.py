import asyncio
import os
import json
import structlog
import random
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import OrderRequestEvent, FillEvent, OrderSubmittedEvent
from datetime import datetime
from uuid import uuid4

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SLIPPAGE_BPS = 5 # 5 basis points
MOCK_PRICE_BTC = 88000.0 # Fallback if we don't have price feed here

# Ideally Execution Engine also listens to Market Data to know current price
# For MVP, we'll assume we get price from somewhere, or just use a mock price/last trade price from Event Bus.
# Let's listen to 'market.trades' or 'market.candles.15m' to update internal price reference.
# Or simpler: listen to 'features.realtime' which has 'close' price.

current_prices = {} # symbol -> float

consumer = KafkaConsumer(
    "orders.request",
    "features.realtime", # To get prices
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='latest',
    group_id="execution-engine-group" 
)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

async def process_loop():
    log.info("Starting Execution Engine (Paper Trading)...")
    
    while True:
        msg_batch = consumer.poll(timeout_ms=100)
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    topic = message.topic
                    data = message.value
                    
                    if topic == "features.realtime":
                        # Update price reference
                        sym = data.get("symbol")
                        feats = data.get("features", {})
                        if sym and "close" in feats:
                            current_prices[sym] = feats["close"]
                            
                    elif topic == "orders.request":
                        order = OrderRequestEvent(**data)
                        log.info("Received Order Request", side=order.side, symbol=order.symbol)
                        
                        # 1. Emit OrderSubmitted
                        submitted = OrderSubmittedEvent(
                            symbol=order.symbol,
                            order_id=order.order_id,
                            status="SUBMITTED"
                        )
                        producer.send("orders.submitted", value=submitted.model_dump(mode='json'))
                        
                        # 2. Simulate Fill
                        # Get price
                        ref_price = current_prices.get(order.symbol, MOCK_PRICE_BTC)
                        
                        # Apply Slippage
                        slippage = ref_price * (SLIPPAGE_BPS / 10000.0)
                        if order.side == "buy":
                            fill_price = ref_price + slippage
                        else:
                            fill_price = ref_price - slippage
                            
                        # Fee (Kraken 0.26%)
                        fee = (fill_price * order.quantity) * 0.0026
                        
                        fill = FillEvent(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            side=order.side,
                            price=fill_price,
                            quantity=order.quantity,
                            fee=fee,
                            fee_currency="USDT", # Approximated
                            timestamp=datetime.utcnow()
                        )
                        
                        # Simulate Latency
                        await asyncio.sleep(random.uniform(0.05, 0.2))
                        
                        producer.send("fills", value=fill.model_dump(mode='json'))
                        log.info("Order Filled", price=fill_price, quantity=order.quantity)

                except Exception as e:
                    log.error("Error processing message", error=str(e))
        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(process_loop())
