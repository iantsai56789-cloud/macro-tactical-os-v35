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
    """
    具備雙源備援機制 (Yahoo Finance + Stooq Failover) 的數據採集器
    自動規避 GitHub Actions 雲端 IP 被阻斷的基礎設施風險
    """
    end_dt = int(datetime.datetime.now().timestamp())
    start_dt = end_dt - (days * 24 * 60 * 60)
    
    # -----------------------------------------------------------------
    # [第一代碼線路] 嘗試透過 Yahoo Finance 採集 (優化模擬瀏覽器標頭)
    # -----------------------------------------------------------------
    yahoo_url = f"https://query1.finance.yahoo.com/v7/finance/download/{ticker}?period1={start_dt}&period2={end_dt}&interval=1d&events=history"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    session = requests.Session()
    try:
        session.get("https://finance.yahoo.com", headers=headers, timeout=5)
        res = session.get(yahoo_url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            df['Date'] = pd.to_datetime(df['Date'])
            df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
            df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
            
            if ticker == "^VIX":
                df = df.dropna(subset=['Close']).sort_values('Date').reset_index(drop=True)
                df['Volume'] = df['Volume'].fillna(0)
            else:
                df = df.dropna(subset=['Close', 'Volume']).sort_values('Date').reset_index(drop=True)
                
            if len(df) >= 30:
                print(f"[+] {ticker} 成功透過 Primary Feeder (Yahoo) 採集。")
                return df
        else:
            print(f"[-] Yahoo 響應失敗 (HTTP {res.status_code})。")
    except Exception as e:
        print(f"[-] Yahoo 採集線路異常 ({e})。")

    # -----------------------------------------------------------------
    # [第二代碼線路] 自動斷路切換：Stooq Terminal Fallback
    # -----------------------------------------------------------------
    print(f"[!] 觸發斷路器：{ticker} 轉向備援數據源 Stooq 進行數據對齊...")
    
    stooq_ticker = "^VIX" if ticker == "^VIX" else f"{ticker}.US"
    stooq_url = f"https://stooq.com/q/d/l/?s={stooq_ticker}&i=d"
    
    try:
        stooq_res = requests.get(stooq_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if stooq_res.status_code == 200 and "Date" in stooq_res.text:
            df = pd.read_csv(io.StringIO(stooq_res.text))
            
            df['Date'] = pd.to_datetime(df['Date'])
            df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
            df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
            
            if ticker == "^VIX":
                df = df.dropna(subset=['Close']).sort_values('Date').reset_index(drop=True)
                df['Volume'] = df['Volume'].fillna(0)
            else:
                df = df.dropna(subset=['Close', 'Volume']).sort_values('Date').reset_index(drop=True)
            
            start_date_bound = datetime.datetime.now() - datetime.timedelta(days=days)
            df = df[df['Date'] >= start_date_bound].reset_index(drop=True)
            
            if len(df) >= 30:
                print(f"[+] {ticker} 成功透過 Secondary Feeder (Stooq) 完成補償採集。")
                return df
            else:
                print(f"[-] Stooq 採集回傳數據量不足 ({len(df)} 筆)。")
        else:
            print(f"[-] Stooq 備援線路失效，狀態碼: {stooq_res.status_code}")
    except Exception as e:
        print(f"[-] 備援線路 Stooq 執行異常: {e}")
        
    return None

def main():
    print("[+] 啟動 v3.7 Systematic Portfolio Optimizer (Lite Risk Parity) ...")
    
    # 1. 獲取大盤與 VIX 數據
    spy_df = fetch_historical_data("SPY", days=150)
    vix_df = fetch_historical_data("^VIX", days=10)
    
    if spy_df is None or len(spy_df) < 90 or vix_df is None or len(vix_df) == 0:
        print("[-] 無法取得基準大盤數據，引擎終止。")
        return

    spy_df['Return'] = spy_df['Close'].pct_change()
    current_vix = float(vix_df['Close'].iloc[-1])

    spy_20d_ret = float((spy_df['Close'].iloc[-1] - spy_df['Close'].iloc[-20]) / spy_df['Close'].iloc[-20])
    spy_20d_vol = float(spy_df['Return'].tail(20).std() * math.sqrt(252))
    spy_ru = spy_20d_ret / spy_20d_vol if spy_20d_vol > 0 else 0.0

    # 2. 建立同步的時間序列與戰術流向矩陣
    asset_data_dict = {}
    tactical_flow_layer = {}
    
    for key, info in BASKETS.items():
        df = fetch_historical_data(info["anchor"], days=150)
        if df is not None and len(df) >= 90:
            df['Return'] = df['Close'].pct_change()
            asset_data_dict[key] = df
            
            vol_20d = float(df['Return'].tail(20).std() * math.sqrt(252))
            ret_20d = float((df['Close'].iloc[-1] - df['Close'].iloc[-20]) / df['Close'].iloc[-20])
            ru_asset = ret_20d / vol_20d if vol_20d > 0 else 0.0
            
            merged = pd.merge(df[['Date', 'Return']], spy_df[['Date', 'Return']], on='Date', suffixes=('_asset', '_spy')).tail(60)
            cov_m = np.cov(merged['Return_asset'], merged['Return_spy'])
            beta = float(cov_m[0, 1] / cov_m[1, 1]) if cov_m[1, 1] > 0 else 1.0
            alpha_flow = ru_asset - (beta * spy_ru)
            
            # 引入 VIX 風險稅扣分機制 (Risk Penalty)
            risk_penalty = vol_20d * (current_vix / 20.0)
            final_score = alpha_flow - risk_penalty
            
            tactical_flow_layer[key] = {
                "name": info["name"],
                "anchor_ticker": info["anchor"],
                "alpha_flow_score": round(alpha_flow, 4),
                "dynamic_beta": round(beta, 2),
                "annual_volatility": round(vol_20d, 4),
                "risk_penalty": round(risk_penalty, 4),
                "final_score": round(final_score, 4)
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
        global_risk_budget *= 0.60

    # 5. 數值編碼逼近法求解風險平價權重 (Iterative Risk Parity Solver)
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

    # 7. 建立機構級結構化 Payload
    output_payload = {
        "metadata": {
            "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            "engine_version": "v3.7_Covariance_Risk_Optimization_Engine"
        },
        "slow_macro_brain": {
            "current_vix": round(current_vix, 2),
            "macro_regime_status": macro_regime,
            "global_risk_budget": round(global_risk_budget, 2),
            "correlation_regime_status": correlation_regime,
            "matrix_average_correlation": round(avg_correlation, 4)
        },
        "tactical_flow_layer": tactical_flow_layer,
        "portfolio_output": portfolio_output
    }

    # 安全覆寫寫入本地 JSON 檔案
    with open("macro_metrics.json", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        
    print(f"[+] v3.7 矩陣優化引擎執行完畢。當前體制: {macro_regime}，相關性防護: {correlation_regime}({round(avg_correlation, 2)})。")

if __name__ == "__main__":
    main()
