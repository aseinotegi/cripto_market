"""
Regime Detector - Classifies market regime for strategy selection.
Uses hysteresis (buffer) to prevent flip-flopping between regimes.
"""
import os
from typing import Optional
from collections import deque

# Config via environment variables
HIGH_VOL_ATR_PCT = float(os.getenv("HIGH_VOL_ATR_PCT", "0.012"))  # 1.2% per 15m candle
ADX_TREND_THRESHOLD = float(os.getenv("ADX_TREND_THRESHOLD", "20"))
REGIME_BUFFER_CANDLES = int(os.getenv("REGIME_BUFFER_CANDLES", "2"))  # Anti-flip buffer


class RegimeDetector:
    """
    Detects market regime based on technical indicators.
    
    Regimes:
    - HIGH_VOL: High volatility, avoid trading
    - TREND_UP: Uptrend, use trend-following strategy
    - RANGE: Sideways market, use mean reversion strategy
    """
    
    def __init__(self):
        # History of detected regimes per symbol for hysteresis
        self._regime_history: dict[str, deque] = {}
    
    def _get_history(self, symbol: str) -> deque:
        """Get regime history for a symbol, creating if needed."""
        if symbol not in self._regime_history:
            self._regime_history[symbol] = deque(maxlen=10)
        return self._regime_history[symbol]
    
    def detect_regime_raw(self, features: dict) -> str:
        """
        Detect regime without hysteresis.
        Returns: HIGH_VOL, TREND_UP, or RANGE
        """
        atr_pct = features.get('atr_pct', 0)
        close = features.get('close', 0)
        ema_20 = features.get('ema_20', 0)
        ema_50 = features.get('ema_50', 0)
        adx = features.get('adx_14', 0)
        
        # 1. HIGH_VOL check first (safety first)
        if atr_pct >= HIGH_VOL_ATR_PCT:
            return "HIGH_VOL"
        
        # 2. TREND_UP conditions
        is_price_above_ema50 = close > ema_50
        is_ema20_above_ema50 = ema_20 > ema_50
        is_adx_strong = adx >= ADX_TREND_THRESHOLD
        
        if is_price_above_ema50 and is_ema20_above_ema50 and is_adx_strong:
            return "TREND_UP"
        
        # 3. Default to RANGE
        return "RANGE"
    
    def detect(self, features: dict, symbol: str) -> str:
        """
        Detect regime with hysteresis buffer.
        
        Hysteresis: Requires REGIME_BUFFER_CANDLES consecutive candles 
        showing the same new regime before switching.
        """
        raw_regime = self.detect_regime_raw(features)
        history = self._get_history(symbol)
        
        # Get current (previous) regime
        current_regime = history[-1] if history else "RANGE"
        
        # Add raw detection to history
        history.append(raw_regime)
        
        # Check if we should switch regime (hysteresis)
        if len(history) >= REGIME_BUFFER_CANDLES:
            # Look at last N detections
            recent = list(history)[-REGIME_BUFFER_CANDLES:]
            
            # All must agree to switch
            if all(r == raw_regime for r in recent):
                return raw_regime
        
        # Not enough consecutive, keep current regime
        return current_regime
    
    def get_regime_info(self, features: dict, symbol: str) -> dict:
        """Get detailed regime information for logging/display."""
        raw = self.detect_regime_raw(features)
        final = self.detect(features, symbol)
        
        return {
            "regime": final,
            "regime_raw": raw,
            "atr_pct": features.get('atr_pct', 0),
            "adx_14": features.get('adx_14', 0),
            "close": features.get('close', 0),
            "ema_20": features.get('ema_20', 0),
            "ema_50": features.get('ema_50', 0),
            "thresholds": {
                "high_vol_atr_pct": HIGH_VOL_ATR_PCT,
                "adx_trend": ADX_TREND_THRESHOLD,
                "buffer_candles": REGIME_BUFFER_CANDLES
            }
        }


# Singleton instance
_detector: Optional[RegimeDetector] = None

def get_regime_detector() -> RegimeDetector:
    """Get singleton RegimeDetector instance."""
    global _detector
    if _detector is None:
        _detector = RegimeDetector()
    return _detector
