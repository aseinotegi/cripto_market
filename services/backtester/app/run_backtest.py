import vectorbt as vbt
import pandas as pd
import numpy as np

def run_backtest():
    print("Loading data...")
    try:
        # Load Data
        df = pd.read_csv("btc_15m.csv", index_col=0, parse_dates=True)
        # Handle MultiIndex columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        close = df['Close']
        high = df['High']
        low = df['Low']
        
        print(f"Data Loaded. {len(close)} candles from {close.index[0]} to {close.index[-1]}")
        
        # --- Strategy Logic ---
        # 1. Indicators
        rsi = vbt.RSI.run(close, window=14)
        
        # 2. Signals
        # Entry: RSI < 30
        entries = rsi.rsi_below(30)
        
        # Exit: RSI > 70
        exits = rsi.rsi_above(70)
        
        # 3. Portfolio Simulation
        # Fees: 0.26% = 0.0026
        # Slippage: 0.05% = 0.0005
        print("Running Simulation (RSI Reversion)...")
        portfolio = vbt.Portfolio.from_signals(
            close,
            entries,
            exits,
            sl_stop=0.05, # 5% Stop Loss
            fees=0.0026,
            slippage=0.0005,
            freq='15m',
            init_cash=10000.0
        )
        
        # 4. Metrics
        print("\n--- Strategy Stats ---")
        print(portfolio.stats())
        
        # Optional: Plot
        # portfolio.plot().show() 
        
    except FileNotFoundError:
        print("Error: btc_15m.csv not found. Run download_data.py first.")
    except Exception as e:
        print(f"Error running backtest: {e}")

if __name__ == "__main__":
    run_backtest()
