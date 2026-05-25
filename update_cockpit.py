import io
import json
import datetime
import requests
import pandas as pd

BASKETS = {
    "AI_Semiconductor": {"name": "AI 半導體族群", "anchor": "SMH", "components": ["SMH", "NVDA", "TSM", "AVGO", "AMD"]},
    "Financial_Value": {"name": "高殖利率金融風格", "anchor": "XLF", "components": ["XLF", "JPM", "BAC", "WFC", "KRE"]},
    "Long_Treasury": {"name": "長端美債避險", "anchor": "TLT", "components": ["TLT", "IEF", "SHY"]}
}

def fetch_historical_data(ticker, days=120):
    end_dt = int(datetime.datetime.now().timestamp())
    start_dt = end_dt - (days * 24 * 60 * 60)
    url = f"https://query1.finance.yahoo.com/v7/finance/download/{ticker}?period1={start_dt}&period2={end_dt}&interval=1d&events=history"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
            df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
            return df.dropna(subset=['Close', 'Volume'])
    except Exception:
        pass
    return None

def main():
    print("[+] 啟動 v3.5 Proxy Flow 核心量化引擎...")
    spy_df = fetch_historical_data("SPY", days=120)
    if spy_df is None or len(spy_df) < 60: return

    flow_matrix = {}
    for sector_name, info in BASKETS.items():
        anchor, components, display_name = info["anchor"], info["components"], info["name"]
        anchor_df = fetch_historical_data(anchor, days=120)
        if anchor_df is None or len(anchor_df) < 60: continue
            
        min_len = min(len(anchor_df), len(spy_df))
        price_ratio = pd.Series(anchor_df['Close'].tail(min_len).values / spy_df['Close'].tail(min_len).values)
        
        ema5 = price_ratio.ewm(span=5, adjust=False).mean()
        ema20 = price_ratio.ewm(span=20, adjust=False).mean()
        ema60 = price_ratio.ewm(span=60, adjust=False).mean()
        
        fast_rs, slow_rs = float(ema5.iloc[-1] - ema20.iloc[-1]), float(ema20.iloc[-1] - ema60.iloc[-1])
        regime = "STRUCTURAL_RETREAT"
        if fast_rs > 0 and slow_rs > 0: regime = "STRONG_CONTINUATION"
        elif fast_rs > 0 and slow_rs <= 0: regime = "TACTICAL_SQUEEZE"
        elif fast_rs <= 0 and slow_rs > 0: regime = "HEALTHY_PULLBACK"

        volume_expansion = float(anchor_df['Volume'].iloc[-1] / anchor_df['Volume'].tail(20).mean()) if anchor_df['Volume'].tail(20).mean() > 0 else 1.0
        trend_alignment = 1 if (anchor_df['Close'].iloc[-1] > anchor_df['Close'].ewm(span=20, adjust=False).mean().iloc[-1] > anchor_df['Close'].ewm(span=60, adjust=False).mean().iloc[-1]) else 0

        passed = 0
        for comp in components:
            comp_df = fetch_historical_data(comp, days=40)
            if comp_df is not None and len(comp_df) >= 20 and comp_df['Close'].iloc[-1] > comp_df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]:
                passed += 1
                    
        flow_matrix[sector_name] = {
            "name": display_name, "anchor_ticker": anchor,
            "core_relative_strength": {"fast_rs": round(fast_rs, 6), "slow_rs": round(slow_rs, 6), "persistence_regime": regime},
            "confirmation_volume_expansion": round(volume_expansion, 2), "structure_trend_alignment": trend_alignment, "breadth_diffusion_score": round(passed / len(components), 2)
        }

    with open("macro_metrics.json", "w", encoding="utf-8") as f:
        json.dump({"metadata": {"timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), "engine_version": "v3.5_Proxy_Flow_Engine"}, "fast_tactical_flow_matrix": flow_matrix}, f, indent=4, ensure_ascii=False)
    print("[+] 數據寫入完成。")

if __name__ == "__main__":
    main()
