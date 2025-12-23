"""
Execution Engine - Paper Trading with Stop-Loss and Trailing Support
Handles order execution, position management, and stop-loss checking.
"""
import asyncio
import os
import json
import structlog
import random
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import OrderRequestEvent, FillEvent, OrderSubmittedEvent
from common.position_store import get_position_store
from datetime import datetime
from uuid import uuid4

log = structlog.get_logger()
position_store = get_position_store()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "5"))
K_ATR_STOP = float(os.getenv("K_ATR_STOP", "2.5"))  # Trailing stop multiplier
MOCK_PRICE_BTC = 88000.0

# Portfolio State (Start with $100)
class Portfolio:
    def __init__(self, initial_cash=100.0):
        self.cash = initial_cash
        self.positions = {}  # symbol -> quantity
        self.start_equity = initial_cash
        
    def get_equity(self, current_prices: dict):
        equity = self.cash
        for sym, qty in self.positions.items():
            price = current_prices.get(sym, 0)
            equity += qty * price
        return equity

portfolio = Portfolio(initial_cash=100.0)

consumer = KafkaConsumer(
    "orders.request",
    "features.realtime",
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='latest',
    group_id="execution-engine-group"
)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

current_prices = {}
current_features = {}  # symbol -> features dict

def check_stop_loss(symbol: str, low: float, close: float, atr: float):
    """Check if stop loss is hit and update trailing."""
    pos_info = position_store.get_position_info(symbol)
    
    if pos_info["qty"] <= 0 or pos_info["stop_loss_price"] is None:
        return False
    
    stop_price = pos_info["stop_loss_price"]
    
    # Check if stop hit
    if low <= stop_price:
        log.info("STOP LOSS HIT", symbol=symbol, low=low, stop=stop_price)
        close_position(symbol, close, reason="STOP_HIT")
        return True
    
    # Update trailing stop (only moves up)
    if atr > 0:
        new_stop = close - (K_ATR_STOP * atr)
        if position_store.update_stop_loss(symbol, new_stop):
            log.info("Trailing stop updated", symbol=symbol, new_stop=new_stop)
    
    return False

def close_position(symbol: str, price: float, reason: str = "SIGNAL"):
    """Close a position and emit fill."""
    pos_info = position_store.get_position_info(symbol)
    qty = pos_info["qty"]
    
    if qty <= 0:
        return
    
    # Apply slippage (sell gets worse price)
    slippage = price * (SLIPPAGE_BPS / 10000.0)
    fill_price = price - slippage
    
    # Fee
    fee = (fill_price * qty) * 0.0026
    
    # Update portfolio
    portfolio.cash += (fill_price * qty - fee)
    portfolio.positions[symbol] = 0
    
    # Emit Fill
    fill = FillEvent(
        order_id=uuid4(),
        symbol=symbol,
        side="sell",
        price=fill_price,
        quantity=qty,
        fee=fee,
        fee_currency="USDT",
        timestamp=datetime.utcnow()
    )
    producer.send("fills", value=fill.model_dump(mode='json'))
    
    # Clear position info in Redis
    position_store.clear_position_info(symbol)
    
    log.info("Position Closed", symbol=symbol, qty=qty, price=fill_price, reason=reason)

async def process_loop():
    log.info("Starting Execution Engine (Paper Trading - $100 Portfolio)...", k_atr_stop=K_ATR_STOP)
    
    last_portfolio_emit = 0
    
    while True:
        msg_batch = consumer.poll(timeout_ms=100)
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    topic = message.topic
                    data = message.value
                    
                    if topic == "features.realtime":
                        sym = data.get("symbol")
                        feats = data.get("features", {})
                        if sym and "close" in feats:
                            current_prices[sym] = feats["close"]
                            current_features[sym] = feats
                            
                            # Check stop-loss on every candle update
                            low = feats.get("low", feats["close"])
                            atr = feats.get("atr_14", 0)
                            check_stop_loss(sym, low, feats["close"], atr)
                        
                        # Emit Portfolio Update periodically
                        now = datetime.utcnow().timestamp()
                        if now - last_portfolio_emit > 1.0:
                            equity = portfolio.get_equity(current_prices)
                            pnl = equity - portfolio.start_equity
                            pnl_pct = (pnl / portfolio.start_equity) * 100
                            
                            # Include position details with stop_loss
                            positions_detail = {}
                            for sym, qty in portfolio.positions.items():
                                if qty > 0:
                                    pos_info = position_store.get_position_info(sym)
                                    positions_detail[sym] = {
                                        "qty": qty,
                                        "avg_price": pos_info.get("avg_price", 0),
                                        "stop_loss_price": pos_info.get("stop_loss_price"),
                                        "unrealized_pnl": (current_prices.get(sym, 0) - pos_info.get("avg_price", 0)) * qty
                                    }
                            
                            update = {
                                "timestamp": now,
                                "equity": equity,
                                "cash": portfolio.cash,
                                "pnl": pnl,
                                "pnl_pct": pnl_pct,
                                "positions": positions_detail
                            }
                            producer.send("portfolio.updates", value=update)
                            last_portfolio_emit = now
                    
                    elif topic == "orders.request":
                        order = OrderRequestEvent(**data)
                        
                        # Idempotency check
                        order_id_str = str(order.order_id)
                        if position_store.is_order_processed(order_id_str):
                            log.info("Skipping duplicate order", order_id=order_id_str)
                            continue
                        
                        log.info("Received Order Request", side=order.side, symbol=order.symbol)
                        
                        # Emit OrderSubmitted
                        submitted = OrderSubmittedEvent(
                            symbol=order.symbol,
                            order_id=order.order_id,
                            status="SUBMITTED"
                        )
                        producer.send("orders.submitted", value=submitted.model_dump(mode='json'))
                        
                        # Get price
                        ref_price = current_prices.get(order.symbol, MOCK_PRICE_BTC)
                        
                        # Apply Slippage
                        slippage = ref_price * (SLIPPAGE_BPS / 10000.0)
                        if order.side == "buy":
                            fill_price = ref_price + slippage
                        else:
                            fill_price = ref_price - slippage
                        
                        # Fee
                        fee = (fill_price * order.quantity) * 0.0026
                        
                        fill = FillEvent(
                            order_id=order.order_id,
                            symbol=order.symbol,
                            side=order.side,
                            price=fill_price,
                            quantity=order.quantity,
                            fee=fee,
                            fee_currency="USDT",
                            timestamp=datetime.utcnow()
                        )
                        
                        # Update Portfolio
                        cost = fill_price * order.quantity
                        if order.side == "buy":
                            portfolio.cash -= (cost + fee)
                            portfolio.positions[order.symbol] = portfolio.positions.get(order.symbol, 0) + order.quantity
                            
                            # Calculate initial stop loss from order or use ATR
                            atr = current_features.get(order.symbol, {}).get("atr_14", 0)
                            stop_price = getattr(order, 'stop_loss_price', None)
                            if stop_price is None and atr > 0:
                                stop_price = fill_price - (K_ATR_STOP * atr)
                            
                            # Get strategy/regime from order if available
                            strategy_id = getattr(order, 'strategy_id', 'unknown')
                            regime = getattr(order, 'regime', 'unknown')
                            
                            # Store full position info
                            position_store.set_position_info(
                                order.symbol,
                                qty=order.quantity,
                                avg_price=fill_price,
                                stop_loss_price=stop_price,
                                strategy_id=strategy_id,
                                regime_at_entry=regime
                            )
                            position_store.set_signal_state(order.symbol, "LONG")
                            
                            log.info("Position Opened", symbol=order.symbol, qty=order.quantity, 
                                    price=fill_price, stop=stop_price)
                        else:
                            portfolio.cash += (cost - fee)
                            current_qty = portfolio.positions.get(order.symbol, 0)
                            new_qty = max(0, current_qty - order.quantity)
                            portfolio.positions[order.symbol] = new_qty
                            
                            if new_qty == 0:
                                position_store.clear_position_info(order.symbol)
                            else:
                                # Partial close - update qty
                                pos_info = position_store.get_position_info(order.symbol)
                                position_store.set_position_info(
                                    order.symbol,
                                    qty=new_qty,
                                    avg_price=pos_info["avg_price"],
                                    stop_loss_price=pos_info.get("stop_loss_price"),
                                    strategy_id=pos_info.get("strategy_id"),
                                    regime_at_entry=pos_info.get("regime_at_entry")
                                )
                        
                        # Mark order as processed
                        position_store.mark_order_processed(order_id_str)
                        
                        # Simulate Latency
                        await asyncio.sleep(random.uniform(0.05, 0.2))
                        
                        producer.send("fills", value=fill.model_dump(mode='json'))
                        log.info("Order Filled", price=fill_price, quantity=order.quantity, balance=portfolio.cash)

                except Exception as e:
                    log.error("Error processing message", error=str(e))
        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(process_loop())
