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
    # Ensure all required columns exist, including the new net_flow_usd
    required = ["date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct", "binance_net_flow_usd"]
    for col in required:
        if col not in df.columns:
            df[col] = 0.0
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date").reset_index(drop=True)

def get_defillama_data():
    url = "https://defillama.com/cex/binance-cex"
    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin", "mobile": False})
    r = scraper.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    
    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    data = json.loads(script_tag.string)
    page_props = data.get("props", {}).get("pageProps", {})
    
    # Extract Assets
    chains = page_props.get("currentTvlByChain", {})
    total_assets = float(sum(chains.values()))
    
    # Extract Net Flow (Latest point in historical flow data)
    # totalNetFlows is a list of [timestamp, usd_value]
    flow_history = page_props.get("totalNetFlows", [])
    latest_net_flow = float(flow_history[-1][1]) if flow_history else 0.0
    
    return total_assets, latest_net_flow

def get_total_crypto_mcap_today() -> float:
    url = "https://api.coingecko.com/api/v3/global"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
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
        print("✅ Today already present.")
    else:
        assets, net_flow = get_defillama_data()
        mcap = get_total_crypto_mcap_today()
        share = (assets / mcap) * 100.0
        
        new_row = pd.DataFrame({
            "date": [today], "total_mcap_usd": [mcap], 
            "binance_assets_usd": [assets], "binance_market_share_pct": [share],
            "binance_net_flow_usd": [net_flow]
        })
        df = pd.concat([df, new_row], ignore_index=True)

    # Save Data
    df.to_csv(OUTPUT_RAW_CSV, index=False)

    # Plot 1: Market Share
    plt.figure(figsize=(10, 5))
    plt.plot(df["date"], df["binance_market_share_pct"], color="blue", label="Market Share %")
    plt.title("Binance Market Share")
    plt.grid(True, alpha=0.3)
    plt.savefig(CHART_SHARE)
    plt.close()

    # Plot 2: Net Flows (Bar Chart)
    plt.figure(figsize=(10, 5))
    colors = ['green' if x >= 0 else 'red' for x in df["binance_net_flow_usd"]]
    plt.bar(df["date"], df["binance_net_flow_usd"] / 1e6, color=colors)
    plt.axhline(0, color='black', linewidth=0.8)
    plt.title("Binance 24h Net Flows (Millions USD)")
    plt.ylabel("USD (Millions)")
    plt.grid(True, alpha=0.2)
    plt.savefig(CHART_FLOW)
    plt.close()

    print("✅ Successfully updated charts and data.")

if __name__ == "__main__":
    main()
