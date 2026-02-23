import json

import time

from datetime import datetime, timezone



import pandas as pd

import matplotlib.pyplot as plt

import requests

import cloudscraper

from bs4 import BeautifulSoup



# =========================

# CONFIG (edit if needed)

# =========================

HISTORICAL_CSV = "binance_market_share_history.csv"   # your existing historicals file

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

    """

    Accepts either:

      - raw columns: date,total_mcap_usd,binance_assets_usd,binance_market_share_pct

      - pretty columns: date,Total MCAP,Binance Assets,Binance Market Share

    and returns the raw schema.

    """

    cols = {c.strip(): c for c in df.columns}



    # normalize date column

    if "date" not in [c.lower() for c in df.columns]:

        # try common variants

        for c in df.columns:

            if "date" in c.lower():

                df = df.rename(columns={c: "date"})

                break



    # if already raw schema:

    raw_needed = {"date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct"}

    if raw_needed.issubset(set(df.columns)):

        pass

    else:

        # try map from pretty schema

        mapping = {}

        for c in df.columns:

            cl = c.lower().strip()

            if cl in ["total mcap", "total_mcap", "total market cap", "total mcap (bn)", "total mcap bn"]:

                mapping[c] = "total_mcap_usd"

            elif cl in ["binance assets", "binance_assets", "binance assets (bn)", "binance assets bn"]:

                mapping[c] = "binance_assets_usd"

            elif cl in ["binance market share", "binance_market_share", "binance market share %", "binance market share pct"]:

                mapping[c] = "binance_market_share_pct"

        if mapping:

            df = df.rename(columns=mapping)



    # final check

    missing = [c for c in ["date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct"] if c not in df.columns]

    if missing:

        raise ValueError(

            f"Historical CSV missing required columns: {missing}\n"

            f"Found columns: {list(df.columns)}\n"

            f"Expected either raw schema: {list(raw_needed)} or pretty schema: "

            f"['date','Total MCAP','Binance Assets','Binance Market Share']"

        )



    df["date"] = pd.to_datetime(df["date"]).dt.date

    df = df.sort_values("date").reset_index(drop=True)

    return df





# =========================

# 1) Load historical

# =========================

def load_historical(path: str) -> pd.DataFrame:

    df = pd.read_csv(path)

    df = _standardize_columns(df)

    return df





# =========================

# 2) Fetch Binance assets today (DeFiLlama page scrape)

# =========================

def get_binance_assets_today_defillama() -> float:

    url = "https://defillama.com/cex/binance-cex"



    scraper = cloudscraper.create_scraper(

        browser={"browser": "chrome", "platform": "darwin", "mobile": False}

    )

    r = scraper.get(url, timeout=30, headers={"User-Agent": USER_AGENT})

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



    total_balance = float(sum(chains.values()))

    return total_balance





# =========================

# 3) Fetch total crypto mcap today (CoinGecko Global)

# =========================

def get_total_crypto_mcap_today() -> float:

    url = "https://api.coingecko.com/api/v3/global"

    headers = {"User-Agent": USER_AGENT}



    # light retry

    last_err = None

    for _ in range(3):

        try:

            r = requests.get(url, headers=headers, timeout=20)

            r.raise_for_status()

            data = r.json()

            return float(data["data"]["total_market_cap"]["usd"])

        except Exception as e:

            last_err = e

            time.sleep(1.2)



    raise RuntimeError(f"CoinGecko /global failed after retries: {last_err}")





# =========================

# 4) Upsert today's row

# =========================

def upsert_today(df_hist: pd.DataFrame) -> pd.DataFrame:

    today = _today_utc_date()



    if today in df_hist["date"].values:

        print("✅ Today already present — no update needed.")

        return df_hist



    print("🚀 Fetching today's Binance assets (DeFiLlama) + total mcap (CoinGecko)...")

    binance_assets = get_binance_assets_today_defillama()

    time.sleep(0.5)

    total_mcap = get_total_crypto_mcap_today()



    share_pct = (binance_assets / total_mcap) * 100.0



    new_row = pd.DataFrame(

        {

            "date": [today],

            "total_mcap_usd": [total_mcap],

            "binance_assets_usd": [binance_assets],

            "binance_market_share_pct": [share_pct],

        }

    )



    df_updated = pd.concat([df_hist, new_row], ignore_index=True)

    df_updated = df_updated.sort_values("date").reset_index(drop=True)



    print("✅ Added today's row")

    return df_updated





# =========================

# 5) Pretty output + summary.json

# =========================

def make_pretty(df_raw: pd.DataFrame) -> pd.DataFrame:

    df = df_raw.copy()

    df = df.rename(

        columns={

            "total_mcap_usd": "Total MCAP",

            "binance_assets_usd": "Binance Assets",

            "binance_market_share_pct": "Binance Market Share",

        }

    )



    # billions

    df["Total MCAP"] = (df["Total MCAP"] / 1e9).round(2)

    df["Binance Assets"] = (df["Binance Assets"] / 1e9).round(2)

    df["Binance Market Share"] = df["Binance Market Share"].round(3)

    return df





def write_summary(df_plot: pd.DataFrame) -> dict:

    # df_plot must have date + binance_market_share_pct

    df_plot = df_plot.dropna(subset=["binance_market_share_pct"]).copy()



    today_row = df_plot.iloc[-1]

    avg = float(df_plot["binance_market_share_pct"].mean())

    today_val = float(today_row["binance_market_share_pct"])

    diff_pp = today_val - avg

    diff_pct = (diff_pp / avg) * 100.0 if avg != 0 else 0.0



    summary = {

        "as_of_date": str(today_row["date"]),

        "today_share_pct": today_val,

        "average_share_pct": avg,

        "diff_pp": diff_pp,

        "diff_pct_vs_avg": diff_pct,

        "points_count": int(len(df_plot)),

    }



    with open(OUTPUT_SUMMARY, "w") as f:

        json.dump(summary, f, indent=2)



    return summary





# =========================

# 6) Plot

# =========================

def plot_chart(df_raw: pd.DataFrame, days_to_plot: int = DAYS_TO_PLOT) -> dict:

    df = df_raw.copy()

    df = df.dropna(subset=["binance_market_share_pct"]).sort_values("date").reset_index(drop=True)



    if days_to_plot and len(df) > days_to_plot:

        df_plot = df.tail(days_to_plot).copy()

    else:

        df_plot = df.copy()



    avg = float(df_plot["binance_market_share_pct"].mean())

    today_val = float(df_plot.iloc[-1]["binance_market_share_pct"])

    diff_pp = today_val - avg

    diff_pct = (diff_pp / avg) * 100.0 if avg != 0 else 0.0



    plt.figure(figsize=(12, 6))

    plt.plot(df_plot["date"], df_plot["binance_market_share_pct"], label="Daily %")

    # average line must be red

    plt.axhline(avg, linestyle="--", linewidth=2, color="red", label=f"Average ({avg:.2f}%)")



    plt.title("Binance Market Share of Total Crypto Market Cap")

    plt.ylabel("% Share")

    plt.xlabel("Date")

    plt.grid(True)



    # Put legend in upper left, then put annotation BELOW it (no overlap)

    plt.legend(loc="upper left")



    annotation = f"Today vs Avg: {diff_pp:+.2f}pp ({diff_pct:+.1f}%)"

    # y=0.86 keeps it below legend area in most cases; tweak if you change legend location

    plt.gca().text(

        0.02,

        0.86,

        annotation,

        transform=plt.gca().transAxes,

        fontsize=11,

        bbox=dict(boxstyle="round,pad=0.3", alpha=0.2),

    )



    plt.tight_layout()

    plt.savefig(OUTPUT_CHART, dpi=160)

    plt.close()



    return {

        "avg": avg,

        "today": today_val,

        "diff_pp": diff_pp,

        "diff_pct": diff_pct,

        "last_date": str(df_plot.iloc[-1]["date"]),

        "rows_plotted": int(len(df_plot)),

    }





# =========================

# MAIN

# =========================

def main():

    print("Loading historical...")

    df_hist = load_historical(HISTORICAL_CSV)



    df_updated = upsert_today(df_hist)



    # save raw updated series (good for chart + github pages)

    df_updated.to_csv(OUTPUT_RAW_CSV, index=False)



    # pretty output for humans

    df_pretty = make_pretty(df_updated)

    df_pretty.to_csv(OUTPUT_PRETTY_CSV, index=False)



    # plot + summary

    plot_stats = plot_chart(df_updated, DAYS_TO_PLOT)

    summary = write_summary(df_updated.tail(DAYS_TO_PLOT) if DAYS_TO_PLOT else df_updated)



    print("✅ Wrote:", OUTPUT_RAW_CSV, OUTPUT_PRETTY_CSV, OUTPUT_CHART, OUTPUT_SUMMARY)

    print("Plot stats:", plot_stats)

    print("Summary:", summary)





if __name__ == "__main__":

    main(). 
