import os
from datetime import datetime, timezone

import pandas as pd
import matplotlib.pyplot as plt
import requests
import cloudscraper
from bs4 import BeautifulSoup
import json

# =========================
# CONFIG
# =========================
HISTORICAL_CSV = "binance_market_share_history.csv"
OUTPUT_CSV = "binance_market_share_history.csv"  # overwrite in-place (simple for Pages)
OUTPUT_PNG = "chart.png"
DAYS_TO_PLOT = 365

# Column names we will enforce in the saved CSV
COL_DATE = "date"
COL_TOTAL = "Total MCAP"
COL_BINANCE = "Binance Assets"
COL_SHARE = "Binance Market Share"

# =========================
# Fetchers (TODAY)
# =========================
def get_binance_assets_today_defillama_sum() -> float:
    """
    Uses DefiLlama Next.js payload to get 'currentTvlByChain' and sums to total assets.
    Returns USD float.
    """
    url = "https://defillama.com/cex/binance-cex"
    scraper = cloudscraper.create_scraper()
    r = scraper.get(url, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag is None or not script_tag.string:
        raise RuntimeError("Could not find __NEXT_DATA__ (blocked or structure changed).")

    data = json.loads(script_tag.string)
    page_props = data.get("props", {}).get("pageProps", {})
    chains = page_props.get("currentTvlByChain")
    if chains is None:
        raise KeyError(f"'currentTvlByChain' not found. Keys: {list(page_props.keys())}")

    # chains is { "BTC": ..., "ETH": ..., ... } values in USD
    total_balance = float(sum(chains.values()))
    return total_balance


def get_total_crypto_mcap_today_coingecko() -> float:
    """
    CoinGecko global endpoint (no key usually needed) for total market cap USD.
    """
    url = "https://api.coingecko.com/api/v3/global"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    return float(data["data"]["total_market_cap"]["usd"])


# =========================
# Load + normalize historical CSV
# =========================
def load_historical(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing {path}. Put your historical CSV in the repo root named '{HISTORICAL_CSV}'."
        )

    df = pd.read_csv(path)

    # Accept either your old internal cols or the renamed “pretty” cols
    # Old: date,total_mcap_usd,binance_assets_usd,binance_market_share_pct
    # New: date,Total MCAP,Binance Assets,Binance Market Share
    if "total_mcap_usd" in df.columns:
        df = df.rename(columns={
            "total_mcap_usd": COL_TOTAL,
            "binance_assets_usd": COL_BINANCE,
            "binance_market_share_pct": COL_SHARE,
        })

    # Some CSVs may have "Date" instead of "date"
    if "Date" in df.columns and COL_DATE not in df.columns:
        df = df.rename(columns={"Date": COL_DATE})

    required = {COL_DATE, COL_TOTAL, COL_BINANCE, COL_SHARE}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Historical CSV is missing columns: {missing}. Columns found: {list(df.columns)}")

    df[COL_DATE] = pd.to_datetime(df[COL_DATE]).dt.date

    # Ensure numeric
    for c in [COL_TOTAL, COL_BINANCE, COL_SHARE]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_values(COL_DATE).reset_index(drop=True)
    return df


# =========================
# Upsert today's row
# =========================
def upsert_today(df_hist: pd.DataFrame) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()

    if today in set(df_hist[COL_DATE].values):
        print("✅ Today already present — no update needed.")
        return df_hist

    print("🚀 Fetching today's data...")
    binance_assets = get_binance_assets_today_defillama_sum()
    total_mcap = get_total_crypto_mcap_today_coingecko()

    share_pct = (binance_assets / total_mcap) * 100.0

    new_row = pd.DataFrame({
        COL_DATE: [today],
        COL_TOTAL: [total_mcap],
        COL_BINANCE: [binance_assets],
        COL_SHARE: [share_pct],
    })

    df_updated = pd.concat([df_hist, new_row], ignore_index=True)
    df_updated = df_updated.sort_values(COL_DATE).reset_index(drop=True)
    print("✅ Added today's row")
    return df_updated


# =========================
# Plot + annotate
# =========================
def plot_chart(df: pd.DataFrame, days_to_plot: int = DAYS_TO_PLOT, out_png: str = OUTPUT_PNG) -> None:
    df_plot = df.copy()
    df_plot["dt"] = pd.to_datetime(df_plot[COL_DATE])

    if days_to_plot is not None and days_to_plot > 0 and len(df_plot) > days_to_plot:
        df_plot = df_plot.iloc[-days_to_plot:].copy()

    avg = df_plot[COL_SHARE].mean()
    today_val = df_plot[COL_SHARE].iloc[-1]

    # Difference in percentage points and relative to average
    diff_pp = today_val - avg
    rel = (diff_pp / avg) * 100.0 if avg != 0 else float("nan")

    plt.figure(figsize=(12, 6))
    plt.plot(df_plot["dt"], df_plot[COL_SHARE], label="Daily %")
    plt.axhline(avg, linestyle="--", linewidth=2, color="red", label=f"Average ({avg:.2f}%)")

    plt.title("Binance Market Share of Total Crypto Market Cap")
    plt.ylabel("% Share")
    plt.xlabel("Date")
    plt.grid(True)

    # Legend top-left; then put annotation just BELOW it (so they don't overlap)
    plt.legend(loc="upper left")

    sign = "+" if diff_pp >= 0 else "-"
    text = f"Today vs Avg: {sign}{abs(diff_pp):.2f}pp ({sign}{abs(rel):.1f}%)"
    plt.gca().text(
        0.015, 0.88, text, transform=plt.gca().transAxes,
        va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.3", alpha=0.15)
    )

    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()

    print(f"✅ Wrote chart: {out_png}")
    print(text)


def format_for_humans(df: pd.DataFrame) -> pd.DataFrame:
    """
    Optional: store values in BILLIONS for readability.
    Keeps % as percent (not fraction).
    """
    out = df.copy()
    out[COL_TOTAL] = (out[COL_TOTAL] / 1e9).round(2)
    out[COL_BINANCE] = (out[COL_BINANCE] / 1e9).round(2)
    out[COL_SHARE] = out[COL_SHARE].round(3)
    return out


def main():
    df = load_historical(HISTORICAL_CSV)
    df = upsert_today(df)

    # Save “human-friendly” CSV in billions (recommended)
    df_out = format_for_humans(df)
    df_out.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ Wrote CSV: {OUTPUT_CSV}")

    plot_chart(df, DAYS_TO_PLOT, OUTPUT_PNG)


if __name__ == "__main__":
    main()
