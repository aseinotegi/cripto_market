-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Candles (15m Timeframe)
CREATE TABLE IF NOT EXISTS candles_15m (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    trades INT,
    PRIMARY KEY (time, symbol)
);

-- Turn into hypertable (partition by time)
SELECT create_hypertable('candles_15m', 'time', if_not_exists => TRUE);

-- Features (Indicator Values)
CREATE TABLE IF NOT EXISTS features (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    value DOUBLE PRECISION,
    PRIMARY KEY (time, symbol, feature_name)
);
SELECT create_hypertable('features', 'time', if_not_exists => TRUE);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    order_id UUID PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL, -- BUY, SELL
    type TEXT NOT NULL, -- MARKET, LIMIT
    quantity DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION,
    status TEXT NOT NULL, -- PENDING, SUBMITTED, FILLED, CANCELED, REJECTED
    leverage INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fills (Executions)
CREATE TABLE IF NOT EXISTS fills (
    fill_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    fee DOUBLE PRECISION NOT NULL,
    fee_currency TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL
);

-- PnL Snapshots (Equity Curve)
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    time TIMESTAMPTZ NOT NULL,
    total_equity DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION,
    unrealized_pnl DOUBLE PRECISION,
    positions_value DOUBLE PRECISION,
    cash_balance DOUBLE PRECISION,
    currency TEXT DEFAULT 'USDT'
);
SELECT create_hypertable('pnl_snapshots', 'time', if_not_exists => TRUE);

-- Risk Events (Rejection Logs)
CREATE TABLE IF NOT EXISTS risk_events (
    time TIMESTAMPTZ NOT NULL,
    reason TEXT,
    event_data JSONB
);
SELECT create_hypertable('risk_events', 'time', if_not_exists => TRUE);
