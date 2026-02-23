import json
import time
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
CHART_SHARE = "chart.png"
CHART_FLOW = "net_flow_chart.png"
OUTPUT_SUMMARY = "summary.json"

DAYS_TO_PLOT = 365
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def _today_utc_date():
    return datetime.now(timezone.utc).date()

def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure the new net flow column exists
    if "binance_net_flow_usd" not in df.columns:
        df["binance_net_flow_usd"] = 0.0
    
    # Existing normalization logic
    mapping = {
        "Total MCAP": "total_mcap_usd",
        "Binance Assets": "binance_assets_usd",
        "Binance Market Share": "binance_market_share_pct"
    }
    df = df.rename(columns=mapping)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date").reset_index(drop=True)

def get_defillama_data():
    """Fetches both Total Assets and 24h Net Flow from DeFiLlama."""
    url = "https://defillama.com/cex/binance-cex"
    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin", "mobile": False})
    r = scraper.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    data = json.loads(script_tag.string)
    page_props = data.get("props", {}).get("pageProps", {})

    # 1. Total Assets
    chains = page_props.get("currentTvlByChain", {})
    total_assets = float(sum(chains.values()))

    # 2. 24h Net Flow (The value from the table in your screenshot)
    # We pull 'inflow24h' which is the stable summary figure
    net_flow = float(page_props.get("inflow24h", 0.0))
    
    return total_assets, net_flow

def get_total_crypto_mcap_today() -> float:
    url = "https://api.coingecko.com/api/v3/global"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return float(r.json()["data"]["total_market_cap"]["usd"])

def main():
    print("Loading historical...")
    try:
        df = pd.read_csv(HISTORICAL_CSV)
    except FileNotFoundError:
        df = pd.DataFrame(columns=["date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct", "binance_net_flow_usd"])
    
    df = _standardize_columns(df)
    today = _today_utc_date()

    if today in df["date"].values:
        print("✅ Today's data already recorded.")
    else:
        print("🚀 Fetching latest data from DeFiLlama and CoinGecko...")
        assets, net_flow = get_defillama_data()
        mcap = get_total_crypto_mcap_today()
        share = (assets / mcap) * 100.0
        
        new_row = pd.DataFrame({
            "date": [today], 
            "total_mcap_usd": [mcap], 
            "binance_assets_usd": [assets], 
            "binance_market_share_pct": [share],
            "binance_net_flow_usd": [net_flow]
        })
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(HISTORICAL_CSV, index=False)
        print(f"✅ Added: Assets=${assets/1e9:.2f}B, Net Flow=${net_flow/1e6:.2f}M")

    # Save outputs
    df.to_csv(OUTPUT_RAW_CSV, index=False)

    # --- CHART 1: Market Share ---
    plt.figure(figsize=(12, 6))
    plt.plot(df["date"], df["binance_market_share_pct"], label="Market Share %", linewidth=2)
    plt.title("Binance Market Share of Total Crypto Market Cap", fontsize=14)
    plt.ylabel("% Share")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHART_SHARE, dpi=160)
    plt.close()

    # --- CHART 2: Net Flows (Bar Chart) ---
    plt.figure(figsize=(12, 6))
    # Filter only days where we have net flow data (non-zero or recent)
    df_flow = df[df["binance_net_flow_usd"] != 0].copy()
    if not df_flow.empty:
        colors = ['#26a69a' if x >= 0 else '#ef5350' for x in df_flow["binance_net_flow_usd"]]
        plt.bar(df_flow["date"], df_flow["binance_net_flow_usd"] / 1e6, color=colors, alpha=0.8)
        plt.axhline(0, color='black', linewidth=0.8)
        plt.title("Binance Daily Net Flows (USD Millions)", fontsize=14)
        plt.ylabel("USD (Millions)")
        plt.grid(axis='y', linestyle='--', alpha=0.5)
    else:
        plt.text(0.5, 0.5, "Waiting for more data points...", ha='center')
        
    plt.tight_layout()
    plt.savefig(CHART_FLOW, dpi=160)
    plt.close()

    print("✅ All charts updated successfully.")
    
    
if __name__ == "__main__":
    main()
