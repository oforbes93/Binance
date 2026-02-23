import json
import time
from datetime import datetime, timezone
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import requests
import cloudscraper
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================
MS_CSV = "binance_market_share_history.csv"
NF_CSV = "binance_net_flows.csv"
CHART_SHARE = "chart.png"
CHART_FLOW = "net_flow_chart.png"
DAYS_TO_PLOT = 365
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36..."

def _today_utc_date():
    return datetime.now(timezone.utc).date()

# ... [Keep get_defillama_data() and get_total_crypto_mcap_today() from previous version] ...

def main():
    # 1. Load Data
    try:
        df_ms = pd.read_csv(MS_CSV)
        df_ms['date'] = pd.to_datetime(df_ms['date']).dt.date
    except FileNotFoundError:
        df_ms = pd.DataFrame(columns=["date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct"])

    try:
        df_nf = pd.read_csv(NF_CSV)
        df_nf['date'] = pd.to_datetime(df_nf['date']).dt.date
    except FileNotFoundError:
        df_nf = pd.DataFrame(columns=["date", "binance_net_flow_usd"])

    # 2. Daily Update Logic
    today = _today_utc_date()
    if today not in df_ms["date"].values:
        assets, net_flow_val = get_defillama_data()
        mcap = get_total_crypto_mcap_today()
        share = (assets / mcap) * 100.0
        
        pd.concat([df_ms, pd.DataFrame({"date": [today], "total_mcap_usd": [mcap], "binance_assets_usd": [assets], "binance_market_share_pct": [share]})]).to_csv(MS_CSV, index=False)
        pd.concat([df_nf, pd.DataFrame({"date": [today], "binance_net_flow_usd": [net_flow_val]})]).to_csv(NF_CSV, index=False)
        # Reload to ensure data is fresh for plotting
        df_ms = pd.read_csv(MS_CSV); df_ms['date'] = pd.to_datetime(df_ms['date']).dt.date
        df_nf = pd.read_csv(NF_CSV); df_nf['date'] = pd.to_datetime(df_nf['date']).dt.date

    # 3. Merge for Plotting
    df = pd.merge(df_ms, df_nf, on="date", how="left").fillna(0)
    df_plot = df.tail(DAYS_TO_PLOT).copy()

    # --- RESTORED CHART 1: Market Share with Average ---
    avg = float(df_plot["binance_market_share_pct"].mean())
    today_val = float(df_plot.iloc[-1]["binance_market_share_pct"])
    diff_pp = today_val - avg
    diff_pct = (diff_pp / avg) * 100.0 if avg != 0 else 0.0

    plt.figure(figsize=(12, 6))
    plt.plot(df_plot["date"], df_plot["binance_market_share_pct"], label="Daily %", color="tab:blue")
    plt.axhline(avg, linestyle="--", linewidth=2, color="red", label=f"Average ({avg:.2f}%)")

    plt.title("Binance Market Share of Total Crypto Market Cap")
    plt.ylabel("% Share")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="upper left")

    # Re-adding the annotation below the legend
    plt.gca().text(0.02, 0.86, f"Today vs Avg: {diff_pp:+.2f}pp ({diff_pct:+.1f}%)", 
                   transform=plt.gca().transAxes, fontsize=11, bbox=dict(boxstyle="round,pad=0.3", alpha=0.2))

    plt.tight_layout()
    plt.savefig(CHART_SHARE, dpi=160)
    plt.close()

    # --- CHART 2: Net Flows (Bar Chart) ---
    plt.figure(figsize=(12, 6))
    df_flow_recent = df.tail(30).copy()
    colors = ['#26a69a' if x >= 0 else '#ef5350' for x in df_flow_recent["binance_net_flow_usd"]]
    plt.bar(df_flow_recent["date"], df_flow_recent["binance_net_flow_usd"] / 1e6, color=colors)
    plt.axhline(0, color='black', linewidth=0.8)
    
    # Custom Legend for Flows
    plt.legend(handles=[mpatches.Patch(color='#26a69a', label='Net Inflow'), 
                        mpatches.Patch(color='#ef5350', label='Net Outflow')], loc="upper left")

    plt.title("Binance Daily Net Flows (USD Millions)")
    plt.ylabel("USD (Millions)")
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(CHART_FLOW, dpi=160)
    plt.close()

if __name__ == "__main__":
    main()
