import os
import json
import time
from datetime import datetime, timezone

# 1. FORCE HEADLESS MODE (Must be before pyplot import)
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt

import pandas as pd
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
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# =========================
# Helpers
# =========================
def _today_utc_date():
    return datetime.now(timezone.utc).date()

def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure column names match the expected raw schema."""
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
# API Fetchers
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
        except Exception as e:
            print(f"CoinGecko retry... {e}")
            time.sleep(5)
    raise RuntimeError("CoinGecko API failed after 3 retries.")

# =========================
# Core Logic
# =========================
def upsert_today(df_hist: pd.DataFrame) -> pd.DataFrame:
    today = _today_utc_date()
    
    # If today already exists, we skip the API calls but return the DF
    if today in df_hist["date"].values:
        print(f"✅ Data for {today} already exists. Proceeding to refresh chart/files.")
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
        # Ensure date is date object, drop duplicates, and sort
        df_updated["date"] = pd.to_datetime(df_updated["date"]).dt.date
        df_updated = df_updated.drop_duplicates(subset=['date'], keep='last').sort_values("date")
        return df_updated.reset_index(drop=True)
    except Exception as e:
        print(f"❌ Failed to fetch new data: {e}")
        return df_hist

def plot_chart(df_raw: pd.DataFrame):
    """Generates the PNG chart and handles cleanup for GitHub Actions."""
    # Reset Matplotlib state
    plt.clf()
    plt.close('all')

    df = df_raw.copy()
    df = df.dropna(subset=["binance_market_share_pct"]).tail(DAYS_TO_PLOT)
    
    if df.empty:
        print("⚠️ No data available to plot.")
        return

    avg = df["binance_market_share_pct"].mean()
    latest_val = df["binance_market_share_pct"].iloc[-1]
    diff = latest_val - avg
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df["date"], df["binance_market_share_pct"], label="Daily %", color='#007bff', linewidth=2)
    ax.axhline(avg, linestyle="--", color="red", label=f"Average ({avg:.2f}%)")
    
    ax.set_title("Binance Market Share of Total Crypto Market Cap", fontsize=14, pad=15)
    ax.set_ylabel("% Share")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")

    # Add text annotation
    annotation = f"Latest: {latest_val:.2f}% (Avg: {avg:.2f}%)"
    ax.text(0.02, 0.85, annotation, transform=ax.transAxes, fontsize=10, 
            bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.5))

    plt.tight_layout()
    
    # Remove old file if exists to force a fresh write
    if os.path.exists(OUTPUT_CHART):
        os.remove(OUTPUT_CHART)
        
    plt.savefig(OUTPUT_CHART, dpi=160)
    plt.close(fig)
    print("📈 Chart saved successfully.")

# =========================
# MAIN
# =========================
def main():
    # 1. Load Data
    if not os.path.exists(HISTORICAL_CSV):
        print(f"❌ Error: {HISTORICAL_CSV} not found. Creating empty template.")
        df_hist = pd.DataFrame(columns=["date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct"])
    else:
        df_hist = pd.read_csv(HISTORICAL_CSV)
        df_hist = _standardize_columns(df_hist)

    # 2. Update Data
    df_updated = upsert_today(df_hist)

    # 3. Save Files (Updating timestamps even if no new data)
    df_updated.to_csv(HISTORICAL_CSV, index=False)
    df_updated.to_csv(OUTPUT_RAW_CSV, index=False)
    
    # Create Pretty Version
    df_pretty = df_updated.copy()
    df_pretty["Total MCAP (Bn)"] = (df_pretty["total_mcap_usd"] / 1e9).round(2)
    df_pretty["Binance Assets (Bn)"] = (df_pretty["binance_assets_usd"] / 1e9).round(2)
    df_pretty["Market Share %"] = df_pretty["binance_market_share_pct"].round(3)
    df_pretty[["date", "Total MCAP (Bn)", "Binance Assets (Bn)", "Market Share %"]].to_csv(OUTPUT_PRETTY_CSV, index=False)

    # 4. Save Summary JSON
    last_row = df_updated.iloc[-1]
    summary = {
        "last_updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "date": str(last_row["date"]),
        "share_pct": round(float(last_row["binance_market_share_pct"]), 3),
        "avg_365d": round(float(df_updated.tail(365)["binance_market_share_pct"].mean()), 3)
    }
    with open(OUTPUT_SUMMARY, "w") as f:
        json.dump(summary, f, indent=2)

    # 5. Generate Chart
    plot_chart(df_updated)
    
    print(f"✅ Process finished. Last Date in Data: {df_updated.iloc[-1]['date']}")

if __name__ == "__main__":
    main()
