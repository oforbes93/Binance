import json
import time
from datetime import datetime, timezone
import pandas as pd
import matplotlib.pyplot as plt
import requests
import cloudscraper
from bs4 import BeautifulSoup
import os

# =========================
# CONFIG
# =========================
HISTORICAL_CSV = "binance_market_share_history.csv" 
OUTPUT_PRETTY_CSV = "binance_market_share_history_pretty.csv"
OUTPUT_CHART = "chart.png"
OUTPUT_SUMMARY = "summary.json"

DAYS_TO_PLOT = 365
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# =========================
# Helpers
# =========================
def _today_utc_date():
    return datetime.now(timezone.utc).date()

def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Standardize column names to raw schema
    cols_map = {
        "total mcap": "total_mcap_usd",
        "binance assets": "binance_assets_usd",
        "binance market share": "binance_market_share_pct"
    }
    df.columns = [c.lower().strip() for c in df.columns]
    df = df.rename(columns=cols_map)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date").reset_index(drop=True)

# =========================
# Data Fetchers
# =========================
def get_binance_assets_today_defillama() -> float:
    url = "https://defillama.com/cex/binance-cex"
    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin", "mobile": False})
    r = scraper.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    data = json.loads(BeautifulSoup(r.text, "html.parser").find("script", id="__NEXT_DATA__").string)
    chains = data.get("props", {}).get("pageProps", {}).get("currentTvlByChain")
    return float(sum(chains.values()))

def get_total_crypto_mcap_today() -> float:
    url = "https://api.coingecko.com/api/v3/global"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return float(r.json()["data"]["total_market_cap"]["usd"])

# =========================
# MAIN LOGIC
# =========================
def main():
    if not os.path.exists(HISTORICAL_CSV):
        print(f"❌ Error: {HISTORICAL_CSV} not found. Please restore your backup.")
        return

    # 1. Load data
    df = pd.read_csv(HISTORICAL_CSV)
    df = _standardize_columns(df)

    # 2. Fetch Today
    today = _today_utc_date()
    if today not in df["date"].values:
        print(f"🚀 Fetching data for {today}...")
        try:
            b_assets = get_binance_assets_today_defillama()
            time.sleep(1)
            t_mcap = get_total_crypto_mcap_today()
            
            new_row = pd.DataFrame({
                "date": [today],
                "total_mcap_usd": [t_mcap],
                "binance_assets_usd": [b_assets],
                "binance_market_share_pct": [(b_assets / t_mcap) * 100.0]
            })
            df = pd.concat([df, new_row], ignore_index=True).drop_duplicates('date')
        except Exception as e:
            print(f"⚠️ Fetch failed: {e}")

    # 3. Apply Alignment Fix (on copy for display)
    # We shift the assets to fix the 1-day lag, then recalculate PCT
    df_aligned = df.copy()
    df_aligned['binance_assets_usd'] = df_aligned['binance_assets_usd'].shift(-1)
    df_aligned['binance_market_share_pct'] = (df_aligned['binance_assets_usd'] / df_aligned['total_mcap_usd']) * 100.0
    
    # Clean up any rows where calculation became impossible (NaN)
    df_aligned = df_aligned.dropna(subset=['binance_market_share_pct'])

    # 4. Save Back
    # We save the RAW data (not shifted) to the CSV so we don't lose today's data tomorrow
    df.to_csv(HISTORICAL_CSV, index=False)
    
    # We save the ALIGNED data for the pretty table and chart
    df_pretty = df_aligned.copy()
    df_pretty["total_mcap_usd"] = (df_pretty["total_mcap_usd"] / 1e9).round(2)
    df_pretty["binance_assets_usd"] = (df_pretty["binance_assets_usd"] / 1e9).round(2)
    df_pretty.to_csv(OUTPUT_PRETTY_CSV, index=False)

    # 5. Plotting
    plt.figure(figsize=(12, 6))
    plt.plot(df_aligned["date"], df_aligned["binance_market_share_pct"], label="Daily % (Aligned)")
    plt.title("Binance Market Share")
    plt.grid(True)
    plt.savefig(OUTPUT_CHART, dpi=160)
    plt.close()

    print("✅ Done. CSV updated and Alignment applied to chart.")

if __name__ == "__main__":
    main()
