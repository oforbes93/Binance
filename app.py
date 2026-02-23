import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

def fetch_and_plot_net_flow():
    # DefiLlama endpoint for Binance CEX transparency
    url = "https://api.llama.fi/open-api/historical/binance?usdInflows=true"
    response = requests.get(url).json()
    
    # Extract historical values (date and net inflow in USD)
    data = response.get('historicalValues', [])
    df = pd.DataFrame(data)
    
    # Convert Unix timestamp to readable date and focus on last 30 days
    df['date'] = pd.to_datetime(df['date'], unit='s')
    df = df.tail(30)

    # Plotting
    plt.figure(figsize=(10, 6))
    
    # Color bars: Green for Inflow (>0), Red for Outflow (<0)
    colors = ['#2ebd85' if x > 0 else '#f6465d' for x in df['usdInflow']]
    
    plt.bar(df['date'], df['usdInflow'], color=colors, width=0.8)
    
    # Formatting
    plt.title('Binance 24h Net Exchange Flows (Last 30 Days)', fontsize=14, fontweight='bold')
    plt.ylabel('Net Flow (USD)', fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save to root directory for HTML to find
    plt.savefig('binance_net_flow.png')
    print("Chart updated successfully.")

if __name__ == "__main__":
    fetch_and_plot_net_flow()
