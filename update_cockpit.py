import io
import json
import datetime
import math
import requests
import pandas as pd
import numpy as np

# =====================================================================
# 定義核心機構資產配置籃子 (Asset Allocation Baskets)
# =====================================================================
BASKETS = {
    "AI_Semiconductor": {"name": "AI 半導體族群", "anchor": "SMH"},
    "Financial_Value": {"name": "高殖利率金融風格", "anchor": "XLF"},
    "Long_Treasury": {"name": "長端美債避險", "anchor": "TLT"}
}

def fetch_historical_data(ticker, days=150):
    """安全採集 Yahoo Finance 歷史數據"""
    end_dt = int(datetime.datetime.now().timestamp())
    start_dt = end_dt - (days * 24 * 60 * 60)
    url = f"https://query1.finance.yahoo.com/v7/finance/download/{ticker}?period1={start_dt}&period2={end_dt}&interval=1d&events=history"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            df['Date'] = pd.to_datetime(df['Date'])
            df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
            df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
            df = df.dropna(subset=['Close', 'Volume']).sort_values('Date').reset_index(drop=True)
            return df
    except Exception:
        pass
    return None

def main():
    print("[+] 啟動 v3.6 Cross-Asset Capital Allocation Engine...")
    
    # 1. 獲取基準大盤與恐慌指數數據
    spy_df = fetch_historical_data("SPY", days=150)
    vix_df = fetch_historical_data("^VIX", days=10)
    
    if spy_df is None or len(spy_df) < 90 or vix_df is None or len(vix_df) == 0:
        print("[-] 無法取得大盤基準數據或 VIX 數據，引擎終止。")
        return

    # 計算 SPY 的日收益率
    spy_df['Return'] = spy_df['Close'].pct_change()
    current_vix = float(vix_df['Close'].iloc[-1])
    vix_regime_factor = current_vix / 20.0  # 以 VIX=20 作為基階標準化

    # 計算 SPY 的 20日歸一化風險單位 (RU)
    spy_20d_ret = float((spy_df['Close'].iloc[-1] - spy_df['Close'].iloc[-20]) / spy_df['Close'].iloc[-20])
    spy_20d_vol = float(spy_df['Return'].tail(20).std() * math.sqrt(252))
    spy_ru = spy_20d_ret / spy_20d_vol if spy_20d_vol > 0 else 0.0

    raw_scores = {}
    tactical_flow_matrix = {}

    # 2. 跨資產風險標準化計算核心
    for key, info in BASKETS.items():
        anchor = info["anchor"]
        display_name = info["name"]
        
        asset_df = fetch_historical_data(anchor, days=150)
        if asset_df is None or len(asset_df) < 90:
            continue
            
        asset_df['Return'] = asset_df['Close'].pct_change()
        
        # 🔹 Step 1: 滾動 20日年化波動度與 20日報酬率計算
        vol_20d_annual = float(asset_df['Return'].tail(20).std() * math.sqrt(252))
        ret_20d = float((asset_df['Close'].iloc[-1] - asset_df['Close'].iloc[-20]) / asset_df['Close'].iloc[-20])
        
        ru_asset = ret_20d / vol_20d_annual if vol_20d_annual > 0 else 0.0
        
        # 🔹 Step 2: 雙資產時間序列對齊，計算滾動 60日 Beta 清洗
        merged = pd.merge(asset_df[['Date', 'Return']], spy_df[['Date', 'Return']], on='Date', suffixes=('_asset', '_spy')).tail(60)
        cov_matrix = np.cov(merged['Return_asset'], merged['Return_spy'])
        beta = float(cov_matrix[0, 1] / cov_matrix[1, 1]) if cov_matrix[1, 1] > 0 else 1.0
        
        # 🔹 Step 3: 提取純淨 Alpha Flow
        alpha_flow = ru_asset - (beta * spy_ru)
        
        # 🔹 Step 4: 風險懲罰項計算 (Risk Penalty)
        risk_penalty = vol_20d_annual * vix_regime_factor
        
        # 🔹 Step 5: 最終優化得分模型
        final_score = alpha_flow - risk_penalty
        raw_scores[key] = final_score
        
        # 封裝傳輸矩陣
        tactical_flow_matrix[key] = {
            "name": display_name,
            "anchor_ticker": anchor,
            "risk_adjusted_flow": round(alpha_flow, 4),
            "dynamic_beta": round(beta, 2),
            "annual_volatility": round(vol_20d_annual, 4),
            "risk_penalty": round(risk_penalty, 4),
            "final_score": round(final_score, 4)
        }

    # 3. Softmax 風險預算優化分配層 (Portfolio Allocation Layer)
    if raw_scores:
        exp_scores = {k: math.exp(v) for k, v in raw_scores.items()}
        sum_exp = sum(exp_scores.values())
        portfolio_output = {k: round(exp_v / sum_exp, 4) for k, exp_v in exp_scores.items()}
    else:
        portfolio_output = {}

    # 4. 總體慢速大腦決策邏輯 (Slow Macro Brain)
    macro_regime = "MID_CYCLE_EXPANSION"
    risk_budget = 0.80
    if current_vix > 28:
        macro_regime = "LIQUIDITY_CRISIS"
        risk_budget = 0.35
    elif current_vix > 20:
        macro_regime = "REPAIR_STATIONARY"
        risk_budget = 0.55

    # 5. 輸出機構級結構 Payload
    output_payload = {
        "metadata": {
            "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            "engine_version": "v3.6_Cross_Asset_Capital_Allocation_Engine"
        },
        "slow_macro_brain": {
            "current_vix": current_vix,
            "vix_regime_factor": round(vix_regime_factor, 2),
            "macro_regime_status": macro_regime,
            "global_risk_budget": risk_budget
        },
        "tactical_flow_layer": tactical_flow_matrix,
        "portfolio_output": portfolio_output
    }

    with open("macro_metrics.json", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        
    print(f"[+] v3.6 數據引擎順利落成。當前市場 VIX: {current_vix}，總體風險體制判定為: {macro_regime}。")

if __name__ == "__main__":
    main()
