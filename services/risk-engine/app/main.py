"""
Risk Engine - Validates signals, applies ATR-based position sizing, and creates orders.
Uses PositionStore for equity and position tracking.
"""
import asyncio
import os
import json
import structlog
from kafka import KafkaConsumer, KafkaProducer
from common.schemas import SignalEvent, OrderRequestEvent
from common.position_store import get_position_store
from uuid import uuid4

log = structlog.get_logger()

# Config
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Risk Parameters (Configurable via env vars)
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))  # 0.5% of equity per trade
K_ATR_STOP = float(os.getenv("K_ATR_STOP", "2.5"))  # ATR multiplier for stop distance
MAX_NOTIONAL_PCT = float(os.getenv("MAX_NOTIONAL_PCT", "0.5"))  # Max 50% of equity per position
MIN_TRADE_USDT = float(os.getenv("MIN_TRADE_USDT", "10.0"))  # Minimum trade size
MAX_POSITION_SIZE_USDT = float(os.getenv("MAX_POSITION_SIZE_USDT", "1000.0"))  # Absolute max

position_store = get_position_store()

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


def calculate_position_size(equity: float, price: float, atr: float, stop_price: float = None) -> tuple:
    """
    Calculate position size based on ATR risk sizing.
    
    Formula: qty = (equity * risk_per_trade) / stop_distance
    With caps: max_notional_pct and absolute max
    
    Returns: (quantity, stop_price, sizing_method)
    """
    # Get stop distance
    if stop_price and stop_price > 0:
        stop_distance = abs(price - stop_price)
    elif atr > 0:
        stop_distance = K_ATR_STOP * atr
        stop_price = price - stop_distance
    else:
        # Fallback: use percentage stop (2%)
        stop_distance = price * 0.02
        stop_price = price - stop_distance
    
    # Risk-based sizing
    risk_amount = equity * RISK_PER_TRADE
    
    if stop_distance > 0:
        qty_risk = risk_amount / stop_distance
        sizing_method = "atr_risk"
    else:
        # Fallback to fixed sizing
        qty_risk = MIN_TRADE_USDT / price
        sizing_method = "fallback_fixed"
    
    # Apply max notional cap
    max_notional = equity * MAX_NOTIONAL_PCT
    qty_cap = max_notional / price
    
    # Apply absolute cap
    qty_abs_cap = MAX_POSITION_SIZE_USDT / price
    
    # Take minimum of all caps
    qty = min(qty_risk, qty_cap, qty_abs_cap)
    
    # Ensure minimum trade size
    min_qty = MIN_TRADE_USDT / price
    if qty < min_qty:
        qty = min_qty
        sizing_method = "minimum"
    
    return round(qty, 6), stop_price, sizing_method


async def process_loop():
    log.info("Starting Risk Engine with ATR Sizing...", 
             risk_per_trade=RISK_PER_TRADE, 
             k_atr_stop=K_ATR_STOP,
             max_notional_pct=MAX_NOTIONAL_PCT)
    
    while True:
        msg_batch = consumer.poll(timeout_ms=100)
        
        for tp, messages in msg_batch.items():
            for message in messages:
                try:
                    data = message.value
                    signal = SignalEvent(**data)
                    log.info("Received Signal", type=signal.signal_type, symbol=signal.symbol, 
                            strategy=signal.strategy_id, regime=signal.regime)
                    
                    # --- Get Current State ---
                    pos_info = position_store.get_position_info(signal.symbol)
                    current_qty = pos_info["qty"]
                    equity = position_store.get_equity()
                    
                    # --- Risk Validation ---
                    
                    # STOPPER: Validate ENTRY_LONG only if qty == 0
                    if signal.signal_type == "ENTRY_LONG":
                        if current_qty > 0:
                            log.warning("REJECTING ENTRY - already in position", 
                                       symbol=signal.symbol, current_qty=current_qty)
                            continue
                    
                    # Validate EXIT makes sense
                    if signal.signal_type == "EXIT_LONG":
                        if current_qty <= 0:
                            log.warning("REJECTING EXIT - no position to exit", symbol=signal.symbol)
                            continue
                    
                    # Extract price and ATR from signal
                    price = signal.reason.get("close", 90000.0) if signal.reason else 90000.0
                    atr = signal.reason.get("atr", 0) if signal.reason else 0
                    
                    # --- Calculate Quantity ---
                    side = None
                    quantity = 0
                    stop_price = None
                    
                    if signal.signal_type == "ENTRY_LONG":
                        side = "buy"
                        
                        # ATR-based sizing
                        quantity, stop_price, sizing_method = calculate_position_size(
                            equity=equity,
                            price=price,
                            atr=atr,
                            stop_price=signal.suggested_stop
                        )
                        
                        log.info("ATR Sizing Calculated", 
                                equity=equity,
                                quantity=quantity,
                                stop_price=stop_price,
                                sizing_method=sizing_method,
                                notional=quantity * price)
                        
                    elif signal.signal_type == "EXIT_LONG":
                        side = "sell"
                        quantity = current_qty  # Exit full position
                    
                    if side and quantity > 0:
                        order = OrderRequestEvent(
                            symbol=signal.symbol,
                            signal_id=signal.signal_id,
                            side=side,
                            type="market",
                            quantity=quantity,
                            stop_loss_price=stop_price,
                            strategy_id=signal.strategy_id,
                            regime=signal.regime
                        )
                        producer.send("orders.request", value=order.model_dump(mode='json'))
                        log.info("Approved Order", 
                                side=side, 
                                symbol=signal.symbol, 
                                quantity=quantity, 
                                price_ref=price, 
                                stop=stop_price,
                                notional=quantity * price)
                    
                except Exception as e:
                    log.error("Error processing signal", error=str(e))
        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(process_loop())
