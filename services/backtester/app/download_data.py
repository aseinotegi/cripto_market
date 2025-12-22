import vectorbt as vbt
import pandas as pd
import os

def download_data():
    print("Downloading 60 days of BTC-USD 15m data...")
    try:
        # Yahoo Finance ticker for BTC
        btc_price = vbt.YFData.download(
            "BTC-USD", 
            interval="15m", 
            period="59d" # 60d is max for 15m on YF usually
        ).get()
        
        # Save to CSV
        btc_price.to_csv("btc_15m.csv")
        print(f"Data saved to btc_15m.csv. Rows: {len(btc_price)}")
        
        # Also print head
        print(btc_price.head())
        
    except Exception as e:
        print(f"Error downloading data: {e}")

if __name__ == "__main__":
    download_data()
