import json
import time
from datetime import datetime, timezone
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import requests
import cloudscraper
from bs4 import BeautifulSoup
import os

# =========================
# CONFIG
# =========================
MS_CSV = "binance_market_share_history.csv"   # Your verified market share data
NF_CSV = "binance_net_flows.csv"              # Your new net flow data
CHART_SHARE = "chart.png"
CHART_FLOW = "net_flow_chart.png"
DAYS_TO_PLOT = 365
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def _today_utc_date():
    return datetime.now(timezone.utc).date()

def get_defillama_data():
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
    print("--- STARTING SCRIPT ---")
    
    # 1. Load Data
    try:
        df_ms = pd.read_csv(MS_CSV)
        df_ms['date'] = pd.to_datetime(df_ms['date']).dt.date
        print(f"Loaded {MS_CSV}")
    except FileNotFoundError:
        print(f"ERROR: {MS_CSV} not found.")
        return

    try:
        df_nf = pd.read_csv(NF_CSV)
        df_nf['date'] = pd.to_datetime(df_nf['date']).dt.date
        print(f"Loaded {NF_CSV}")
    except FileNotFoundError:
        print(f"INFO: {NF_CSV} not found, creating new one.")
        df_nf = pd.DataFrame(columns=["date", "binance_net_flow_usd"])

    # 2. Daily Update
    today = _today_utc_date()
    if today not in df_ms["date"].values:
        print("Fetching today's stats...")
        assets, net_flow_val = get_defillama_data()
        mcap = get_total_crypto_mcap_today()
        share = (assets / mcap) * 100.0
        
        # Append and Save
        new_ms = pd.DataFrame({"date": [today], "total_mcap_usd": [mcap], "binance_assets_usd": [assets], "binance_market_share_pct": [share]})
        df_ms = pd.concat([df_ms, new_ms], ignore_index=True)
        df_ms.to_csv(MS_CSV, index=False)
        
        new_nf = pd.DataFrame({"date": [today], "binance_net_flow_usd": [net_flow_val]})
        df_nf = pd.concat([df_nf, new_nf], ignore_index=True)
        df_nf.to_csv(NF_CSV, index=False)
        print("CSV files updated.")

    # 3. Merge & Prep Plot
    df = pd.merge(df_ms, df_nf, on="date", how="left").fillna(0)
    df_plot = df.tail(DAYS_TO_PLOT).copy()

    # --- CHART 1: Market Share ---
    print(f"Generating {CHART_SHARE}...")
    avg = float(df_plot["binance_market_share_pct"].mean())
    today_val = float(df_plot.iloc[-1]["binance_market_share_pct"])
    diff_pp = today_val - avg
    diff_pct = (diff_pp / avg) * 100.0 if avg != 0 else 0.0

    plt.figure(figsize=(12, 6))
    plt.plot(df_plot["date"], df_plot["binance_market_share_pct"], label="Daily %", color="tab:blue")
    plt.axhline(y=avg, color='red', linestyle='--', linewidth=2, label=f"Average ({avg:.2f}%)")
    plt.title("Binance Market Share of Total Crypto Market Cap")
    plt.ylabel("% Share")
    plt.legend(loc="upper left")
    plt.grid(True, alpha=0.3)
    
    annotation = f"Today vs Avg: {diff_pp:+.2f}pp ({diff_pct:+.1f}%)"
    plt.gca().text(0.02, 0.86, annotation, transform=plt.gca().transAxes, 
                   fontsize=11, bbox=dict(boxstyle="round,pad=0.3", alpha=0.2))

    plt.tight_layout()
    plt.savefig(CHART_SHARE, dpi=160)
    plt.close()
    if os.path.exists(CHART_SHARE):
        print(f"SUCCESS: {CHART_SHARE} saved to {os.getcwd()}")

    # --- CHART 2: Net Flows ---
    print(f"Generating {CHART_FLOW}...")
    plt.figure(figsize=(12, 6))
    df_flow_recent = df.tail(30).copy()
    colors = ['#26a69a' if x >= 0 else '#ef5350' for x in df_flow_recent["binance_net_flow_usd"]]
    plt.bar(df_flow_recent["date"], df_flow_recent["binance_net_flow_usd"] / 1e6, color=colors)
    plt.axhline(0, color='black', linewidth=0.8)
    plt.legend(handles=[mpatches.Patch(color='#26a69a', label='Net Inflow'), 
                        mpatches.Patch(color='#ef5350', label='Net Outflow')], loc="upper left")
    plt.title("Binance Daily Net Flows (USD Millions)")
    plt.ylabel("USD (Millions)")
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(CHART_FLOW, dpi=160)
    plt.close()
    
    print("--- SCRIPT COMPLETE ---")

if __name__ == "__main__":
    main()
