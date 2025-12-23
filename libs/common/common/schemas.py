from datetime import datetime
from typing import Optional, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, ConfigDict

# --- Base ---
class BaseEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_time: datetime = Field(default_factory=datetime.utcnow)
    ingest_time: datetime = Field(default_factory=datetime.utcnow)
    symbol: str
    exchange: str = "kraken"
    idempotency_key: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)

# --- Market Data ---
class CandleEvent(BaseEvent):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int
    interval: str = "15m"

# --- Feature/Signal ---
class FeatureVectorEvent(BaseEvent):
    features: dict[str, float]

class SignalEvent(BaseEvent):
    signal_id: str  # Deterministic: hash(strategy|symbol|candle_ts|intent)
    strategy_id: str
    signal_type: Literal["ENTRY_LONG", "EXIT_LONG", "ENTRY_SHORT", "EXIT_SHORT", "NEUTRAL"]
    regime: str = "UNKNOWN"  # TREND_UP, RANGE, HIGH_VOL
    strength: float = 1.0
    reason: dict = {}
    suggested_stop: Optional[float] = None  # Stop loss price from strategy

# --- Execution ---
class OrderRequestEvent(BaseEvent):
    order_id: UUID = Field(default_factory=uuid4)
    signal_id: Optional[str] = None  # Deterministic signal reference
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"]
    quantity: float
    price: Optional[float] = None
    leverage: int = 1
    stop_loss_price: Optional[float] = None  # Initial stop
    strategy_id: Optional[str] = None
    regime: Optional[str] = None

class OrderSubmittedEvent(BaseEvent):
    order_id: UUID
    provider_order_id: Optional[str] = None
    status: str = "SUBMITTED"

class FillEvent(BaseEvent):
    fill_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    side: Literal["buy", "sell"]
    price: float
    quantity: float
    fee: float
    fee_currency: str
    timestamp: datetime

# --- PnL / Risk ---
class PositionSnapshot(BaseEvent):
    total_exposure: float
    open_positions: int
    unrealized_pnl: float

class RiskEvent(BaseEvent):
    check_name: str
    status: Literal["PASSED", "REJECTED", "WARNING"]
    message: str

# --- Portfolio ---
class PortfolioUpdateEvent(BaseModel):
    """Portfolio update event for WebSocket broadcast"""
    timestamp: float
    equity: float
    cash: float
    pnl: float
    pnl_pct: float
    positions: dict[str, float]
    
    model_config = ConfigDict(populate_by_name=True)
