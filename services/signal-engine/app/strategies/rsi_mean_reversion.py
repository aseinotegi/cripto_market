from typing import List, Optional, Dict
from common.schemas import FeatureVectorEvent, SignalEvent
from strategy_interface import Strategy
from datetime import datetime

class RsiMeanReversionStrategy(Strategy):
    def __init__(self):
        super().__init__(strategy_id="rsi_reversion_v1")
        self.last_signal_side: Dict[str, str] = {} # symbol -> 'LONG' | 'NEUTRAL'

    def on_features(self, event: FeatureVectorEvent) -> List[SignalEvent]:
        f = event.features
        symbol = event.symbol
        signals = []
        
        rsi = f.get("rsi_14", 50)
        close = f.get("close", 0)
        
        # Strategy Parameters
        RSI_LOWER = 30
        RSI_UPPER = 70
        
        current_state = self.last_signal_side.get(symbol, 'NEUTRAL')
        
        # ENTRY SIGNAL (Oversold)
        if rsi < RSI_LOWER:
            if current_state != 'LONG':
                signal = SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    signal_type="ENTRY_LONG",
                    strength=1.0 - (rsi/30.0), # Stronger if RSI is lower
                    reason={
                        "rsi": rsi,
                        "threshold": RSI_LOWER,
                        "close": close
                    }
                )
                signals.append(signal)
                self.last_signal_side[symbol] = 'LONG'

        # EXIT SIGNAL (Overbought or Mean Reverted)
        # We exit if RSI > UPPER. 
        # Optional: Exit if RSI > 50 (Aggressive mean reversion).
        # Let's stick to 70 for profit taking.
        elif rsi > RSI_UPPER:
            if current_state == 'LONG':
                signal = SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    signal_type="EXIT_LONG",
                    strength=(rsi-70)/30.0,
                    reason={
                         "reason": "Overbought",
                         "rsi": rsi, 
                         "threshold": RSI_UPPER
                    }
                )
                signals.append(signal)
                self.last_signal_side[symbol] = 'NEUTRAL'

        return signals
