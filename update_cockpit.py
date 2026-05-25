import io
import json
import datetime
import requests
import pandas as pd

# =====================================================================
# 定義核心機構資金監控籃子 (Baskets Definition)
# =====================================================================
BASKETS = {
    "AI_Semiconductor": {
        "name": "AI 半導體族群",
        "anchor": "SMH",
        "components": ["SMH", "NVDA", "TSM", "AVGO", "AMD"]
    },
    "Financial_Value": {
        "name": "高殖利率金融風格",
        "anchor": "XLF",
        "components": ["XLF", "JPM", "BAC", "WFC", "KRE"]
    },
    "Long_Treasury": {
        "name": "長端美債避險",
        "anchor": "TLT",
        "components": ["TLT", "IEF", "SHY"]
    }
}

def fetch_historical_data(ticker, days=120):
    """安全採集 Yahoo Finance 歷史數據"""
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
            df = df.dropna(subset=['Close', 'Volume'])
            return df
    except Exception:
        pass
    return None

def main():
    print("[+] 啟動 v3.5 Proxy Flow 核心量化引擎...")
    
    # 獲取基準大盤數據
    spy_df = fetch_historical_data("SPY", days=120)
    if spy_df is None or len(spy_df) < 60:
        print("[-] 無法取得大盤 SPY 基準，引擎終止。")
        return

    spy_df = spy_df.reset_index(drop=True)
    flow_matrix = {}

    for sector_name, info in BASKETS.items():
        anchor = info["anchor"]
        components = info["components"]
        display_name = info["name"]
        
        anchor_df = fetch_historical_data(anchor, days=120)
        if anchor_df is None or len(anchor_df) < 60:
            continue
            
        anchor_df = anchor_df.reset_index(drop=True)
        
        # 第一層: 雙時間尺度 EMA 混合相對強度
        min_len = min(len(anchor_df), len(spy_df))
        a_close = anchor_df['Close'].tail(min_len).values
        s_close = spy_df['Close'].tail(min_len).values
        
        price_ratio = pd.Series(a_close / s_close)
        
        ema5 = price_ratio.ewm(span=5, adjust=False).mean()
        ema20 = price_ratio.ewm(span=20, adjust=False).mean()
        ema60 = price_ratio.ewm(span=60, adjust=False).mean()
        
        fast_rs = float(ema5.iloc[-1] - ema20.iloc[-1])
        slow_rs = float(ema20.iloc[-1] - ema60.iloc[-1])
        
        regime_status = "UNKNOWN"
        if fast_rs > 0 and slow_rs > 0: regime_status = "STRONG_CONTINUATION"
        elif fast_rs > 0 and slow_rs <= 0: regime_status = "TACTICAL_SQUEEZE"
        elif fast_rs <= 0 and slow_rs > 0: regime_status = "HEALTHY_PULLBACK"
        elif fast_rs <= 0 and slow_rs <= 0: regime_status = "STRUCTURAL_RETREAT"

        # 第二層: 量能擴張倍數
        current_vol = anchor_df['Volume'].iloc[-1]
        ma20_vol = anchor_df['Volume'].tail(20).mean()
        volume_expansion = float(current_vol / ma20_vol) if ma20_vol > 0 else 1.0

        # 第三層: 趨勢排列過濾
        close_p = anchor_df['Close'].iloc[-1]
        p_ema20 = anchor_df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        p_ema60 = anchor_df['Close'].ewm(span=60, adjust=False).mean().iloc[-1]
        trend_alignment = 1 if (close_p > p_ema20 > p_ema60) else 0

        # 第四層: 廣度擴損得分
        passed_components = 0
        for comp in components:
            comp_df = fetch_historical_data(comp, days=40)
            if comp_df is not None and len(comp_df) >= 20:
                c_close = comp_df['Close'].iloc[-1]
                c_ema20 = comp_df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
                if c_close > c_ema20:
                    passed_components += 1
                    
        diffusion_score = float(passed_components / len(components))

        flow_matrix[sector_name] = {
            "name": display_name,
            "anchor_ticker": anchor,
            "core_relative_strength": {
                "fast_rs": round(fast_rs, 6),
                "slow_rs": round(slow_rs, 6),
                "persistence_regime": regime_status
            },
            "confirmation_volume_expansion": round(volume_expansion, 2),
            "structure_trend_alignment": trend_alignment,
            "breadth_diffusion_score": round(diffusion_score, 2)
        }

    output_payload = {
        "metadata": {
            "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            "engine_version": "v3.5_Proxy_Flow_Engine"
        },
        "fast_tactical_flow_matrix": flow_matrix
    }

    with open("macro_metrics.json", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        
    print("[+] Proxy Flow 核心數據計算完成並寫入 json。")

if __name__ == "__main__":
    main()
