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
    strategy_id: str
    signal_type: Literal["ENTRY_LONG", "EXIT_LONG", "ENTRY_SHORT", "EXIT_SHORT", "NEUTRAL"]
    strength: float = 1.0 # 0.0 to 1.0
    reason: dict = {}

# --- Execution ---
class OrderRequestEvent(BaseEvent):
    order_id: UUID = Field(default_factory=uuid4)
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"]
    quantity: float
    price: Optional[float] = None
    leverage: int = 1

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
