"""
Position Store - Redis-based persistent state for positions and signal state.
Eliminates in-memory state that would be lost on service restart.
"""
import os
import redis
from typing import Optional

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class PositionStore:
    """Redis-backed position and signal state store."""
    
    def __init__(self, redis_url: str = REDIS_URL):
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
    
    # --- Position Tracking ---
    def get_position(self, symbol: str) -> float:
        """Get current position quantity for a symbol."""
        val = self.redis.get(f"position:{symbol}")
        return float(val) if val else 0.0
    
    def set_position(self, symbol: str, quantity: float):
        """Set position quantity for a symbol."""
        self.redis.set(f"position:{symbol}", str(quantity))
    
    def add_position(self, symbol: str, delta: float):
        """Add to current position (can be negative for sells)."""
        current = self.get_position(symbol)
        self.set_position(symbol, current + delta)
    
    # --- Signal State Tracking ---
    def get_signal_state(self, symbol: str) -> str:
        """Get current signal state for a symbol (LONG, SHORT, NEUTRAL)."""
        val = self.redis.get(f"signal_state:{symbol}")
        return val if val else "NEUTRAL"
    
    def set_signal_state(self, symbol: str, state: str):
        """Set signal state for a symbol."""
        self.redis.set(f"signal_state:{symbol}", state)
    
    # --- Idempotency / Deduplication ---
    def is_signal_processed(self, signal_id: str) -> bool:
        """Check if a signal has already been processed."""
        return self.redis.sismember("processed_signals", signal_id)
    
    def mark_signal_processed(self, signal_id: str, ttl_seconds: int = 86400):
        """Mark a signal as processed (with 24h TTL by default)."""
        self.redis.sadd("processed_signals", signal_id)
        # Note: SADD doesn't support per-member TTL, we'd need a separate key
        # For simplicity, we just use the set. A cron job could clean old entries.
    
    def is_order_processed(self, order_id: str) -> bool:
        """Check if an order has already been processed."""
        return self.redis.sismember("processed_orders", order_id)
    
    def mark_order_processed(self, order_id: str):
        """Mark an order as processed."""
        self.redis.sadd("processed_orders", order_id)
    
    # --- Full Position Info (with stop-loss, avg_price, etc.) ---
    def get_position_info(self, symbol: str) -> dict:
        """Get full position info including stop_loss, avg_price, etc."""
        key = f"position_info:{symbol}"
        data = self.redis.hgetall(key)
        if not data:
            return {
                "qty": 0.0,
                "avg_price": 0.0,
                "stop_loss_price": None,
                "strategy_id": None,
                "regime_at_entry": None
            }
        return {
            "qty": float(data.get("qty", 0)),
            "avg_price": float(data.get("avg_price", 0)),
            "stop_loss_price": float(data["stop_loss_price"]) if data.get("stop_loss_price") else None,
            "strategy_id": data.get("strategy_id"),
            "regime_at_entry": data.get("regime_at_entry")
        }
    
    def set_position_info(self, symbol: str, qty: float, avg_price: float, 
                          stop_loss_price: float = None, strategy_id: str = None, 
                          regime_at_entry: str = None):
        """Set full position info."""
        key = f"position_info:{symbol}"
        data = {
            "qty": str(qty),
            "avg_price": str(avg_price)
        }
        if stop_loss_price is not None:
            data["stop_loss_price"] = str(stop_loss_price)
        if strategy_id:
            data["strategy_id"] = strategy_id
        if regime_at_entry:
            data["regime_at_entry"] = regime_at_entry
        self.redis.hset(key, mapping=data)
    
    def update_stop_loss(self, symbol: str, new_stop: float):
        """Update stop loss price (for trailing)."""
        key = f"position_info:{symbol}"
        current = self.redis.hget(key, "stop_loss_price")
        current_stop = float(current) if current else 0.0
        # Trailing: only move up, never down
        if new_stop > current_stop:
            self.redis.hset(key, "stop_loss_price", str(new_stop))
            return True
        return False
    
    def clear_position_info(self, symbol: str):
        """Clear position info after closing."""
        self.redis.delete(f"position_info:{symbol}")
        self.set_signal_state(symbol, "NEUTRAL")
        self.set_position(symbol, 0.0)
    
    # --- Equity Tracking ---
    def get_equity(self) -> float:
        """Get current portfolio equity."""
        val = self.redis.get("portfolio:equity")
        return float(val) if val else 100.0  # Default $100
    
    def set_equity(self, equity: float):
        """Set current portfolio equity."""
        self.redis.set("portfolio:equity", str(equity))
    
    def get_cash(self) -> float:
        """Get current cash balance."""
        val = self.redis.get("portfolio:cash")
        return float(val) if val else 100.0
    
    def set_cash(self, cash: float):
        """Set current cash balance."""
        self.redis.set("portfolio:cash", str(cash))


# Singleton instance for easy import
_store: Optional[PositionStore] = None

def get_position_store() -> PositionStore:
    """Get singleton PositionStore instance."""
    global _store
    if _store is None:
        _store = PositionStore()
    return _store
