"""
RSI Mean Reversion Strategy - Uses deterministic signal_id and Redis-backed state.
Only active in RANGE regime.
"""
import hashlib
from typing import List, Optional
from common.schemas import FeatureVectorEvent, SignalEvent
from common.position_store import get_position_store
from strategy_interface import Strategy

def generate_signal_id(strategy_id: str, symbol: str, candle_ts: int, intent: str) -> str:
    """Generate deterministic signal_id from candle data."""
    data = f"{strategy_id}|{symbol}|15m|{candle_ts}|{intent}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]

class RsiMeanReversionStrategy(Strategy):
    def __init__(self):
        super().__init__(strategy_id="rsi_mr_v1")
        self.position_store = get_position_store()

    def on_features(self, event: FeatureVectorEvent, regime: str = "RANGE") -> List[SignalEvent]:
        """Generate signals only in RANGE regime."""
        # Skip if not in RANGE regime
        if regime != "RANGE":
            return []
        
        f = event.features
        symbol = event.symbol
        signals = []
        
        rsi = f.get("rsi_14", 50)
        close = f.get("close", 0)
        atr = f.get("atr_14", 0)
        
        # Get candle timestamp for deterministic signal_id
        candle_ts = int(event.event_time.timestamp()) if hasattr(event.event_time, 'timestamp') else 0
        
        # Strategy Parameters
        RSI_LOWER = 30
        RSI_UPPER = 55  # Exit at mean (50-55), not 70
        
        # Get current state from Redis
        current_state = self.position_store.get_signal_state(symbol)
        
        # ENTRY SIGNAL (Oversold in RANGE)
        if rsi < RSI_LOWER and current_state != 'LONG':
            # Tighter stop in range (1.5 * ATR)
            stop_price = close - (1.5 * atr) if atr > 0 else None
            
            signal_id = generate_signal_id(self.strategy_id, symbol, candle_ts, "ENTRY_LONG")
            signal = SignalEvent(
                signal_id=signal_id,
                strategy_id=self.strategy_id,
                symbol=symbol,
                signal_type="ENTRY_LONG",
                regime=regime,
                strength=1.0 - (rsi / 30.0),
                reason={
                    "rsi": rsi,
                    "threshold": RSI_LOWER,
                    "close": close,
                    "atr": atr
                },
                suggested_stop=stop_price
            )
            signals.append(signal)

        # EXIT SIGNAL (Mean reversion complete or overbought)
        elif rsi > RSI_UPPER and current_state == 'LONG':
            signal_id = generate_signal_id(self.strategy_id, symbol, candle_ts, "EXIT_LONG")
            signal = SignalEvent(
                signal_id=signal_id,
                strategy_id=self.strategy_id,
                symbol=symbol,
                signal_type="EXIT_LONG",
                regime=regime,
                strength=(rsi - 50) / 50.0,
                reason={
                    "reason": "Mean reverted",
                    "rsi": rsi,
                    "threshold": RSI_UPPER
                }
            )
            signals.append(signal)

        return signals
