import json
import time
import os
from datetime import datetime, timezone

import pandas as pd
import matplotlib.pyplot as plt
import requests
import cloudscraper
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================
HISTORICAL_CSV = "binance_market_share_history.csv"
OUTPUT_RAW_CSV = "binance_market_share_history_raw.csv"
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
    # Normalize column names to lowercase for checking
    df.columns = [c.strip() for c in df.columns]
    
    mapping = {
        "total_mcap_usd": ["total mcap", "total_mcap", "total market cap", "total mcap (bn)"],
        "binance_assets_usd": ["binance assets", "binance_assets", "binance assets (bn)"],
        "binance_market_share_pct": ["binance market share", "binance_market_share", "binance market share %", "binance market share pct"]
    }

    new_cols = {}
    for official, variants in mapping.items():
        for col in df.columns:
            if col.lower() in variants or col.lower() == official:
                new_cols[col] = official
    
    df = df.rename(columns=new_cols)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

# =========================
# 1) Fetching Logic
# =========================
def get_binance_assets_today_defillama() -> float:
    url = "https://defillama.com/cex/binance-cex"
    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin", "mobile": False})
    
    r = scraper.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        raise RuntimeError("DeFiLlama page structure changed or blocked.")

    data = json.loads(script_tag.string)
    page_props = data.get("props", {}).get("pageProps", {})
    chains = page_props.get("currentTvlByChain")
    
    if not chains:
        raise KeyError("Could not find TVL data in DeFiLlama JSON.")

    return float(sum(chains.values()))

def get_total_crypto_mcap_today() -> float:
    url = "https://api.coingecko.com/api/v3/global"
    for _ in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            r.raise_for_status()
            return float(r.json()["data"]["total_market_cap"]["usd"])
        except Exception:
            time.sleep(2)
    raise RuntimeError("CoinGecko API failed after retries.")

# =========================
# 2) Data Processing
# =========================
def upsert_today(df_hist: pd.DataFrame) -> pd.DataFrame:
    today = _today_utc_date()
    
    # Check if we already have today's data to avoid redundant API calls
    if today in df_hist["date"].values:
        print(f"✅ Data for {today} already exists. Skipping fetch.")
        return df_hist

    print(f"🚀 Fetching fresh data for {today}...")
    try:
        binance_val = get_binance_assets_today_defillama()
        total_mcap = get_total_crypto_mcap_today()
        share = (binance_val / total_mcap) * 100

        new_row = pd.DataFrame([{
            "date": today,
            "total_mcap_usd": total_mcap,
            "binance_assets_usd": binance_val,
            "binance_market_share_pct": share
        }])

        df_updated = pd.concat([df_hist, new_row], ignore_index=True)
        return df_updated.sort_values("date").drop_duplicates(subset=['date'], keep='last').reset_index(drop=True)
    except Exception as e:
        print(f"❌ Failed to update data: {e}")
        return df_hist

def make_pretty(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df["Total MCAP (Bn)"] = (df["total_mcap_usd"] / 1e9).round(2)
    df["Binance Assets (Bn)"] = (df["binance_assets_usd"] / 1e9).round(2)
    df["Binance Market Share %"] = df["binance_market_share_pct"].round(3)
    return df[["date", "Total MCAP (Bn)", "Binance Assets (Bn)", "Binance Market Share %"]]

def plot_chart(df: pd.DataFrame):
    df = df.dropna(subset=["binance_market_share_pct"]).tail(DAYS_TO_PLOT)
    avg = df["binance_market_share_pct"].mean()
    
    plt.figure(figsize=(12, 6))
    plt.plot(df["date"], df["binance_market_share_pct"], label="Daily %", color='#007bff', linewidth=2)
    plt.axhline(avg, linestyle="--", color="red", label=f"Avg ({avg:.2f}%)")
    
    plt.title("Binance Market Share of Total Crypto Market Cap", fontsize=14)
    plt.ylabel("% Share")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="upper left")
    
    plt.tight_layout()
    plt.savefig(OUTPUT_CHART, dpi=160)
    plt.close()

# =========================
# MAIN
# =========================
def main():
    if not os.path.exists(HISTORICAL_CSV):
        print(f"❌ Error: {HISTORICAL_CSV} not found in root directory.")
        return

    print("Loading historical data...")
    df_hist = pd.read_csv(HISTORICAL_CSV)
    df_hist = _standardize_columns(df_hist)

    # 1. Update
    df_updated = upsert_today(df_hist)

    # 2. Save Raw (This is your database)
    df_updated.to_csv(HISTORICAL_CSV, index=False)
    df_updated.to_csv(OUTPUT_RAW_CSV, index=False)

    # 3. Save Pretty (For humans/GitHub preview)
    df_pretty = make_pretty(df_updated)
    df_pretty.to_csv(OUTPUT_PRETTY_CSV, index=False)

    # 4. Save Summary JSON
    last_row = df_updated.iloc[-1]
    summary = {
        "date": str(last_row["date"]),
        "share_pct": round(float(last_row["binance_market_share_pct"]), 3),
        "avg_pct": round(float(df_updated.tail(DAYS_TO_PLOT)["binance_market_share_pct"].mean()), 3)
    }
    with open(OUTPUT_SUMMARY, "w") as f:
        json.dump(summary, f, indent=2)

    # 5. Plot
    plot_chart(df_updated)
    print(f"✅ Refresh Complete. Latest date: {df_updated.iloc[-1]['date']}")

if __name__ == "__main__":
    main()
