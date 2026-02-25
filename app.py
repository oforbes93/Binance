import json
import time
from datetime import datetime, timezone

import pandas as pd
import matplotlib.pyplot as plt
import requests
import cloudscraper
from bs4 import BeautifulSoup

# =========================
# CONFIG (Fixed filenames)
# =========================
HISTORICAL_CSV = "binance_market_share_history.csv" 
OUTPUT_RAW_CSV = "binance_market_share_history.csv"
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
    if "date" not in [c.lower() for c in df.columns]:
        for c in df.columns:
            if "date" in c.lower():
                df = df.rename(columns={c: "date"})
                break

    mapping = {}
    for c in df.columns:
        cl = c.lower().strip()
        if cl in ["total mcap", "total_mcap_usd", "total market cap"]:
            mapping[c] = "total_mcap_usd"
        elif cl in ["binance assets", "binance_assets_usd"]:
            mapping[c] = "binance_assets_usd"
        elif cl in ["binance market share", "binance_market_share_pct"]:
            mapping[c] = "binance_market_share_pct"
    
    if mapping:
        df = df.rename(columns=mapping)

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    return df

# =========================
# Data Fetchers
# =========================
def get_binance_assets_today_defillama() -> float:
    url = "https://defillama.com/cex/binance-cex"
    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin", "mobile": False})
    r = scraper.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    data = json.loads(script_tag.string)
    page_props = data.get("props", {}).get("pageProps", {})
    chains = page_props.get("currentTvlByChain")
    return float(sum(chains.values()))

def get_total_crypto_mcap_today() -> float:
    url = "https://api.coingecko.com/api/v3/global"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    data = r.json()
    return float(data["data"]["total_market_cap"]["usd"])

# =========================
# Logic & Processing
# =========================
def upsert_today(df_hist: pd.DataFrame) -> pd.DataFrame:
    today = _today_utc_date()
    if today in df_hist["date"].values:
        print("✅ Today already present.")
        return df_hist

    binance_assets = get_binance_assets_today_defillama()
    time.sleep(0.5)
    total_mcap = get_total_crypto_mcap_today()
    share_pct = (binance_assets / total_mcap) * 100.0

    new_row = pd.DataFrame({
        "date": [today],
        "total_mcap_usd": [total_mcap],
        "binance_assets_usd": [binance_assets],
        "binance_market_share_pct": [share_pct],
    })

    df_updated = pd.concat([df_hist, new_row], ignore_index=True)
    return df_updated.sort_values("date").reset_index(drop=True)

def make_pretty(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df = df.rename(columns={
        "total_mcap_usd": "Total MCAP",
        "binance_assets_usd": "Binance Assets",
        "binance_market_share_pct": "Binance Market Share",
    })
    df["Total MCAP"] = (df["Total MCAP"] / 1e9).round(2)
    df["Binance Assets"] = (df["Binance Assets"] / 1e9).round(2)
    df["Binance Market Share"] = df["Binance Market Share"].round(3)
    return df

def plot_chart(df_raw: pd.DataFrame, days_to_plot: int = DAYS_TO_PLOT):
    df = df_raw.tail(days_to_plot).copy()
    avg = float(df["binance_market_share_pct"].mean())
    plt.figure(figsize=(12, 6))
    plt.plot(df["date"], df["binance_market_share_pct"], label="Daily %")
    plt.axhline(avg, linestyle="--", linewidth=2, color="red", label=f"Average ({avg:.2f}%)")
    plt.title("Binance Market Share (Aligned)")
    plt.grid(True)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(OUTPUT_CHART, dpi=160)
    plt.close()

# =========================
# MAIN
# =========================
def main():
    print("Loading historical...")
    df = pd.read_csv(HISTORICAL_CSV)
    df = _standardize_columns(df)

    # --- ALIGNMENT FIX ---
    # Shift Binance assets to correct 1-day reporting lag
    df['binance_assets_usd'] = df['binance_assets_usd'].shift(-1)
    # Recalculate share pct with aligned data
    df['binance_market_share_pct'] = (df['binance_assets_usd'] / df['total_mcap_usd']) * 100.0
    # Drop empty row created by shift
    df = df.dropna(subset=['binance_assets_usd'])
    # ---------------------

    df_updated = upsert_today(df)
    df_updated.to_csv(OUTPUT_RAW_CSV, index=False)
    
    df_pretty = make_pretty(df_updated)
    df_pretty.to_csv(OUTPUT_PRETTY_CSV, index=False)

    plot_chart(df_updated)
    print("✅ Complete.")

if __name__ == "__main__":
    main()
