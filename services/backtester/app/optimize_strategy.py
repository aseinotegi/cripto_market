import vectorbt as vbt
import pandas as pd
import numpy as np

def run_optimization():
    print("Loading data...")
    try:
        # Load Data
        df = pd.read_csv("btc_15m.csv", index_col=0, parse_dates=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df['Close']
        
        # --- Parameter Grid ---
        windows = [14]
        lower_thresholds = [15, 20, 25, 30, 35]
        upper_thresholds = [60, 65, 70, 75, 80, 85]
        
        print(f"Testing RSI Reversion ({len(lower_thresholds) * len(upper_thresholds)} combinations)...")
        
        # --- Vectorized Backtest ---
        rsi = vbt.RSI.run(close, window=windows)
        
        # vbt.RSI.run produces a single column if window is 14.
        # We need to broadcast thresholds against it.
        
        # Parameter Product
        entries = rsi.rsi_below(lower_thresholds, short_name='lower')
        exits = rsi.rsi_above(upper_thresholds, short_name='upper')
        
        # 3. Running Portfolio
        portfolio = vbt.Portfolio.from_signals(
            close,
            entries,
            exits,
            fees=0.0026,
            slippage=0.0005,
            freq='15m',
            init_cash=10000.0,
            sl_stop=0.05 # Add 5% stop loss for safety
        )
        
        # 4. Analysis
        total_return = portfolio.total_return()
        
        print("\n--- Top 5 Configurations ---")
        print(total_return.sort_values(ascending=False).head())
        
        best_idx = total_return.idxmax()
        print(f"\nBest Parameters: {best_idx}")
        print(f"Total Return: {total_return.max()*100:.2f}%")
        
        # Detailed stats for best
        print("\n--- Best Config Stats ---")
        print(portfolio[best_idx].stats())
        
    except FileNotFoundError:
        print("Error: btc_15m.csv not found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_optimization()
