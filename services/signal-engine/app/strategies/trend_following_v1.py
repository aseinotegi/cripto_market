"""
Trend Following Strategy v1 - Donchian Breakout with ATR Trailing Stop.
Only active in TREND_UP regime.
"""
import hashlib
from typing import List
from common.schemas import FeatureVectorEvent, SignalEvent
from common.position_store import get_position_store
from strategy_interface import Strategy


def generate_signal_id(strategy_id: str, symbol: str, candle_ts: int, intent: str) -> str:
    """Generate deterministic signal_id from candle data."""
    data = f"{strategy_id}|{symbol}|15m|{candle_ts}|{intent}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


class TrendFollowingStrategy(Strategy):
    """
    Trend Following Strategy using Donchian Breakout.
    
    Entry (TREND_UP only):
    - close > donchian_high_20 (breakout)
    
    Exit:
    - close < ema_50 (trend invalidation)
    - Trailing stop managed by execution-engine
    """
    
    def __init__(self):
        super().__init__(strategy_id="trend_breakout_v1")
        self.position_store = get_position_store()
        self.k_atr_stop = 2.5  # ATR multiplier for initial stop

    def on_features(self, event: FeatureVectorEvent, regime: str = "TREND_UP") -> List[SignalEvent]:
        """Generate signals only in TREND_UP regime."""
        # Skip if not in TREND_UP regime
        if regime != "TREND_UP":
            return []
        
        f = event.features
        symbol = event.symbol
        signals = []
        
        close = f.get("close", 0)
        ema_50 = f.get("ema_50", 0)
        donchian_high = f.get("donchian_high_20", 0)
        atr = f.get("atr_14", 0)
        
        # Get candle timestamp for deterministic signal_id
        candle_ts = int(event.event_time.timestamp()) if hasattr(event.event_time, 'timestamp') else 0
        
        # Get current state from Redis
        current_state = self.position_store.get_signal_state(symbol)
        pos_info = self.position_store.get_position_info(symbol)
        current_qty = pos_info.get("qty", 0)
        
        # --- ENTRY: Breakout above Donchian High ---
        if current_qty <= 0 and current_state != "LONG":
            # Breakout condition: close > donchian_high_20
            if close > donchian_high and donchian_high > 0:
                # Calculate initial stop loss (2.5 * ATR below close)
                stop_price = close - (self.k_atr_stop * atr) if atr > 0 else None
                
                signal_id = generate_signal_id(self.strategy_id, symbol, candle_ts, "ENTRY_LONG")
                signal = SignalEvent(
                    signal_id=signal_id,
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    signal_type="ENTRY_LONG",
                    regime=regime,
                    strength=1.0,
                    reason={
                        "type": "breakout",
                        "close": close,
                        "donchian_high": donchian_high,
                        "atr": atr,
                        "ema_50": ema_50
                    },
                    suggested_stop=stop_price
                )
                signals.append(signal)
        
        # --- EXIT: Trend Invalidation ---
        elif current_qty > 0 or current_state == "LONG":
            # Exit if close breaks below EMA 50 (trend invalid)
            if close < ema_50 and ema_50 > 0:
                signal_id = generate_signal_id(self.strategy_id, symbol, candle_ts, "EXIT_LONG")
                signal = SignalEvent(
                    signal_id=signal_id,
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    signal_type="EXIT_LONG",
                    regime=regime,
                    strength=1.0,
                    reason={
                        "type": "trend_invalidation",
                        "close": close,
                        "ema_50": ema_50
                    }
                )
                signals.append(signal)

        return signals
