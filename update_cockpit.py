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
    print("[+] 啟動 v3.7 Systematic Portfolio Optimizer (Lite Risk Parity) ...")
    
    # 1. 獲取大盤與 VIX 數據
    spy_df = fetch_historical_data("SPY", days=150)
    vix_df = fetch_historical_data("^VIX", days=10)
    
    if spy_df is None or len(spy_df) < 90 or vix_df is None or len(vix_df) == 0:
        print("[-] 無法取得基準數據，引擎終止。")
        return

    spy_df['Return'] = spy_df['Close'].pct_change()
    current_vix = float(vix_df['Close'].iloc[-1])
    vix_regime_factor = current_vix / 20.0

    spy_20d_ret = float((spy_df['Close'].iloc[-1] - spy_df['Close'].iloc[-20]) / spy_df['Close'].iloc[-20])
    spy_20d_vol = float(spy_df['Return'].tail(20).std() * math.sqrt(252))
    spy_ru = spy_20d_ret / spy_20d_vol if spy_20d_vol > 0 else 0.0

    # 2. 建立同步的時間序列 DataFrame 用於計算矩陣
    asset_data_dict = {}
    tactical_flow_matrix = {}
    
    for key, info in BASKETS.items():
        df = fetch_historical_data(info["anchor"], days=150)
        if df is not None and len(df) >= 90:
            df['Return'] = df['Close'].pct_change()
            asset_data_dict[key] = df
            
            # 延續 v3.6 核心流向指標計算
            vol_20d = float(df['Return'].tail(20).std() * math.sqrt(252))
            ret_20d = float((df['Close'].iloc[-1] - df['Close'].iloc[-20]) / df['Close'].iloc[-20])
            ru_asset = ret_20d / vol_20d if vol_20d > 0 else 0.0
            
            merged = pd.merge(df[['Date', 'Return']], spy_df[['Date', 'Return']], on='Date', suffixes=('_asset', '_spy')).tail(60)
            cov_m = np.cov(merged['Return_asset'], merged['Return_spy'])
            beta = float(cov_m[0, 1] / cov_m[1, 1]) if cov_m[1, 1] > 0 else 1.0
            alpha_flow = ru_asset - (beta * spy_ru)
            
            tactical_flow_matrix[key] = {
                "name": info["name"],
                "anchor_ticker": info["anchor"],
                "alpha_flow_score": round(alpha_flow, 4),
                "dynamic_beta": round(beta, 2),
                "annual_volatility": round(vol_20d, 4)
            }

    # 檢查核心資產數據完整性
    keys = list(BASKETS.keys())
    if not all(k in asset_data_dict for k in keys):
        print("[-] 核心資產數據不齊全，無法進行矩陣優化。")
        return

    # 3. 構建共變異數矩陣與相關性矩陣 (使用過去 60 個交易日)
    merged_returns = pd.DataFrame()
    for k in keys:
        df = asset_data_dict[k][['Date', 'Return']].rename(columns={'Return': k})
        if merged_returns.empty:
            merged_returns = df
        else:
            merged_returns = pd.merge(merged_returns, df, on='Date')

    merged_returns = merged_returns.tail(60).drop(columns=['Date'])
    
    # 計算年化共變異數矩陣 (Covariance Matrix * 252)
    cov_matrix = merged_returns.cov() * 252
    cov_np = cov_matrix.to_numpy()
    
    # 計算相關性矩陣與平均交叉相關度
    corr_matrix = merged_returns.corr()
    avg_correlation = float((corr_matrix.sum().sum() - len(keys)) / (len(keys) * (len(keys) - 1)))

    # 4. 慢速大腦決策與相關性衝擊控制 (Correlation Shock Regime Switch)
    macro_regime = "MID_CYCLE_EXPANSION"
    global_risk_budget = 0.80
    correlation_regime = "NORMAL"

    if current_vix > 28:
        macro_regime = "LIQUIDITY_CRISIS"
        global_risk_budget = 0.35
    elif current_vix > 20:
        macro_regime = "REPAIR_STATIONARY"
        global_risk_budget = 0.55

    # 觸發相關性飆升防禦閘
    if avg_correlation > 0.70:
        correlation_regime = "SHOCK_BREACH"
        global_risk_budget *= 0.60  # 風險預算再防禦性打折

    # 5. 數值逼近法求解風險平價權重 (Iterative Risk Parity Solver)
    n = len(keys)
    w = np.ones(n) / n  # 初始等權重猜測
    lr = 0.1           # 梯度逼近步長
    
    for _ in range(200):
        port_var = w.T @ cov_np @ w
        port_sd = math.sqrt(port_var)
        if port_sd == 0: 
            break
        mrc = (cov_np @ w) / port_sd
        rc = w * mrc
        
        # 計算各資產與平均風險貢獻的缺口
        error = rc - rc.mean()
        
        # 梯度更新並實施約束投影
        w = w - lr * error
        w = np.clip(w, 0.05, 1.0)  # 設定單一資產最低配比 5% 防止極端空倉
        w = w / w.sum()            # 權重歸一化符合 sum(w) = 1

    # 將優化權重陣列轉回字典
    portfolio_output = {keys[i]: round(float(w[i]), 4) for i in range(n)}

    # 若觸發相關性衝擊，實施避險防禦調配 (強制增配安全邊際債券)
    if correlation_regime == "SHOCK_BREACH":
        portfolio_output["Long_Treasury"] = round(min(portfolio_output["Long_Treasury"] + 0.20, 0.80), 4)
        # 剩餘權重按比例等比縮減
        rem_sum = sum(portfolio_output[k] for k in keys if k != "Long_Treasury")
        target_rem = 1.0 - portfolio_output["Long_Treasury"]
        for k in keys:
            if k != "Long_Treasury":
                portfolio_output[k] = round((portfolio_output[k] / rem_sum) * target_rem, 4)

    # 6. 計算各資產最終的實際風險貢獻比例 (用於前端診斷)
    final_port_sd = math.sqrt(w.T @ cov_np @ w)
    final_mrc = (cov_np @ w) / final_port_sd
    final_rc = w * final_mrc
    rc_pct = final_rc / final_rc.sum()

    for i, k in enumerate(keys):
        tactical_flow_layer[k]["portfolio_risk_contribution_pct"] = round(float(rc_pct[i]), 4)

    # 7. 輸出機構級結構 Payload
    output_payload = {
        "metadata": {
            "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            "engine_version": "v3.7_Covariance_Risk_Optimization_Engine"
        },
        "slow_macro_brain": {
            "current_vix": current_vix,
            "macro_regime_status": macro_regime,
            "global_risk_budget": round(global_risk_budget, 2),
            "correlation_regime_status": correlation_regime,
            "matrix_average_correlation": round(avg_correlation, 4)
        },
        "tactical_flow_layer": tactical_flow_layer,
        "portfolio_output": portfolio_output
    }

    with open("macro_metrics.json", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        
    print(f"[+] v3.7 矩陣優化引擎執行完畢。相關性體制: {correlation_regime}({round(avg_correlation, 2)})。")

if __name__ == "__main__":
    main()
