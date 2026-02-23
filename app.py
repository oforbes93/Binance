# =========================
# CONFIG (Add this new line)
# =========================
HISTORICAL_CSV = "binance_market_share_history.csv"
FLOWS_CSV = "binance_net_flows.csv"  # <--- New file for flows

# ... (keep your existing helper functions: _today_utc_date, get_defillama_data, etc.) ...

def main():
    print("Loading historical data...")
    # Load Main History (Graph 1)
    try:
        df = pd.read_csv(HISTORICAL_CSV)
    except FileNotFoundError:
        df = pd.DataFrame(columns=["date", "total_mcap_usd", "binance_assets_usd", "binance_market_share_pct"])
    
    # Load Flows History (Graph 2)
    try:
        df_flows = pd.read_csv(FLOWS_CSV)
    except FileNotFoundError:
        df_flows = pd.DataFrame(columns=["date", "net flows"]) # <--- Your requested headers

    today = _today_utc_date()
    today_str = str(today)

    # CHECK: Have we recorded today yet?
    # Checking df["date"] because if we have one, we usually have both
    if today_str in df["date"].astype(str).values:
        print("✅ Today's data already recorded.")
    else:
        print("🚀 Fetching latest data...")
        assets, net_flow = get_defillama_data()
        mcap = get_total_crypto_mcap_today()
        share = (assets / mcap) * 100.0
        
        # 1. Update Market Share CSV
        new_row_share = pd.DataFrame({
            "date": [today], 
            "total_mcap_usd": [mcap], 
            "binance_assets_usd": [assets], 
            "binance_market_share_pct": [share]
        })
        df = pd.concat([df, new_row_share], ignore_index=True)
        df.to_csv(HISTORICAL_CSV, index=False)

        # 2. Update Net Flows CSV (The separate file)
        new_row_flow = pd.DataFrame({
            "date": [today],
            "net flows": [net_flow]
        })
        df_flows = pd.concat([df_flows, new_row_flow], ignore_index=True)
        df_flows.to_csv(FLOWS_CSV, index=False)
        
        print(f"✅ Data saved to both files.")

    # --- CHART 2: Net Flows (Now using the new df_flows) ---
    plt.figure(figsize=(12, 6))
    if not df_flows.empty:
        # Convert date column to datetime for better plotting
        df_flows["date"] = pd.to_datetime(df_flows["date"])
        
        # Color: Green for positive, Red for negative
        colors = ['#26a69a' if x >= 0 else '#ef5350' for x in df_flows["net flows"]]
        
        plt.bar(df_flows["date"], df_flows["net flows"] / 1e6, color=colors, alpha=0.8)
        plt.axhline(0, color='black', linewidth=0.8)
        plt.title("Binance Daily Net Flows (USD Millions)", fontsize=14)
        plt.ylabel("USD (Millions)")
        plt.grid(axis='y', linestyle='--', alpha=0.5)
    else:
        plt.text(0.5, 0.5, "No flow data found.", ha='center')
        
    plt.tight_layout()
    plt.savefig(CHART_FLOW, dpi=160)
    plt.close()

    print("✅ All charts and CSVs updated successfully.")
