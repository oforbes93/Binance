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
MS_CSV = "binance_market_share_history.csv"   # Primary Market Share file
NF_CSV = "binance_net_flows.csv"              # New Net Flow file
OUTPUT_RAW_CSV = "binance_market_share_history_raw.csv"
OUTPUT_PRETTY_CSV = "binance_market_share_history_pretty.csv"
CHART_SHARE = "chart.png"
CHART_FLOW = "net_flow_chart.png"

DAYS_TO_PLOT = 365
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def _today_utc_date():
    return datetime.now(timezone.utc).date()

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

    chains = page_props.get("currentTvlByChain", {})
    total_assets = float(sum(chains.values()))
    net_flow = float(page_props.get("inflow24h", 0.0))
    
    return total_assets, net_flow

def get_total_crypto_mcap_today() -> float:
    url = "https://api.coingecko.com/api/v3/global"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return float(r.json()["data"]["total_market_cap"]["usd"])

def main():
    print("Loading data sources...")
    # Load Primary Market Share
    try:
        df_ms = pd.read_csv(MS_CSV)
        df_ms['date'] = pd.to_datetime(df_ms['date']).dt.date
    except FileNotFoundError:
        df_ms = pd.DataFrame(columns=["date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct"])

    # Load Net Flows
    try:
        df_nf = pd.read_csv(NF_CSV)
        df_nf['date'] = pd.to_datetime(df_nf['date']).dt.date
    except FileNotFoundError:
        df_nf = pd.DataFrame(columns=["date", "binance_net_flow_usd"])

    today = _today_utc_date()

    # 1. Update Market Share File if needed
    if today not in df_ms["date"].values:
        print("🚀 Fetching today's Market Share data...")
        assets, net_flow_val = get_defillama_data()
        mcap = get_total_crypto_mcap_today()
        share = (assets / mcap) * 100.0
        
        new_ms_row = pd.DataFrame({
            "date": [today], 
            "total_mcap_usd": [mcap], 
            "binance_assets_usd": [assets], 
            "binance_market_share_pct": [share]
        })
        df_ms = pd.concat([df_ms, new_ms_row], ignore_index=True)
        df_ms.to_csv(MS_CSV, index=False)
        
        # 2. Update Net Flow File separately
        new_nf_row = pd.DataFrame({"date": [today], "binance_net_flow_usd": [net_flow_val]})
        df_nf = pd.concat([df_nf, new_nf_row], ignore_index=True)
        df_nf.to_csv(NF_CSV, index=False)
        print(f"✅ Data updated for {today}")

    # 3. Merge data in-memory for plotting
    df_combined = pd.merge(df_ms, df_nf, on="date", how="left").fillna(0)

    # --- CHART 1: Market Share ---
    plt.figure(figsize=(12, 6))
    plt.plot(df_combined["date"], df_combined["binance_market_share_pct"], color="blue", linewidth=2)
    plt.title("Binance Market Share of Total Crypto Market Cap", fontsize=14)
    plt.ylabel("% Share")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHART_SHARE, dpi=160)
    plt.close()

    # --- CHART 2: Net Flows (Bar Chart) ---
    plt.figure(figsize=(12, 6))
    # Only plot non-zero flows or the last 14 days to ensure the chart renders
    df_flow_plot = df_combined.tail(14).copy()
    
    colors = ['#26a69a' if x >= 0 else '#ef5350' for x in df_flow_plot["binance_net_flow_usd"]]
    plt.bar(df_flow_plot["date"], df_flow_plot["binance_net_flow_usd"] / 1e6, color=colors, alpha=0.8)
    plt.axhline(0, color='black', linewidth=0.8)
    plt.title("Binance Daily Net Flows (USD Millions)", fontsize=14)
    plt.ylabel("USD (Millions)")
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(CHART_FLOW, dpi=160)
    plt.close()

    print("✅ All charts updated successfully using separate CSV sources.")

if __name__ == "__main__":
    main()
