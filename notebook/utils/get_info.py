import requests
from bs4 import BeautifulSoup
import sqlite3
import pandas as pd
from statistics import median
from typing import Dict
import numpy as np

def get_finviz_data(symbol: str) -> dict:
    url = f"https://finviz.com/quote.ashx?t={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"[Finviz] 無法取得 {symbol} 頁面。")
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    data = {}

    # 找到財務表格
    table = soup.find("table", class_="snapshot-table2")
    if not table:
        print(f"[Finviz] 找不到財報表格")
        return {}

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        for i in range(0, len(cells), 2):
            key = cells[i].text.strip()
            value = cells[i+1].text.strip()
            data[key] = value

    return data

def get_quarter_medians_and_year_avg(db_path: str, stock: str, year: int) -> Dict[str, float]:
    """
    從資料庫中讀取指定股票在某一年的每日價格，
    並計算每一季的收盤價中位數，以及年度平均（可改為加權平均）。
    """
    conn = sqlite3.connect(db_path)
    query = f"""
        SELECT Date, Close FROM t_{stock.replace('.', '_')}
        WHERE Date BETWEEN '{year}-01-01' AND '{year}-12-31'
    """
    df = pd.read_sql(query, conn, parse_dates=['Date'])
    conn.close()

    if df.empty:
        return {"Q1": None, "Q2": None, "Q3": None, "Q4": None, "YearAvg": None}

    # 加入季度欄位
    df['Quarter'] = df['Date'].dt.quarter

    result = {}
    medians = []
    for q in range(1, 5):
        q_close = df[df['Quarter'] == q]['Close']
        if not q_close.empty:
            q_median = round(median(q_close), 2)
            result[f"Q{q}"] = q_median
            medians.append(q_median)
        else:
            result[f"Q{q}"] = None

    if medians:
        result["YearAvg"] = round(sum(medians) / len(medians), 2)
    else:
        result["YearAvg"] = None

    return result

# 示範呼叫（範例參數）
# result = get_quarter_medians_and_year_avg("stock_data.db", "GOOG", 2023)
# print(result)


def calculate_annualized_std(price_series: pd.Series) -> float:
    """
    計算給定價格序列的年化標準差。
    
    參數:
    price_series (pd.Series): 包含每日收盤價的 Pandas Series。
    
    返回:
    float: 年化標準差。
    """
    # 1. 計算每日報酬率
    daily_returns = price_series.pct_change()
    
    # 2. 計算每日報酬率的標準差
    daily_std = daily_returns.std()
    
    # 3. 進行年化
    annualized_std = daily_std * np.sqrt(252)
    
    return annualized_std

# --- 使用範例 ---
# 假設你的 DataFrame 叫做 stock_df
# stock_df = db_manager.get_stock("AMD", "5y") 

# # 傳入收盤價的 Series
# amd_annualized_volatility = calculate_annualized_std(stock_df['Close'])

# print(f"\nAMD 的五年年化標準差（波動率）為: {amd_annualized_volatility:.2%}")


def calculate_annual_return(price_series: pd.Series) -> float:
    daily_returns = price_series.pct_change().dropna()
    annualized_std = daily_returns.std() * np.sqrt(252)
    annualized_return = daily_returns.mean() * 252
    return annualized_return

    
def calculate_sharpe_ratio(price_series: pd.Series, risk_free_rate: float) -> float:
    """
    計算給定價格序列的年化夏普值。

    參數:
    price_series (pd.Series): 包含每日收盤價的 Pandas Series。
    risk_free_rate (float): 年化的無風險利率 (例如：3% 就輸入 0.03)。

    返回:
    float: 年化夏普值。
    """
    # 1. 計算每日報酬率
    daily_returns = price_series.pct_change().dropna()
    
    # --- 計算夏普值的三大要素 ---
    
    # (a) 計算年化標準差 (風險)
    annualized_std = daily_returns.std() * np.sqrt(252)
    
    # (b) 計算年化報酬率
    # 這裡使用算術平均日報酬率來年化，是常見做法
    annualized_return = daily_returns.mean() * 252
    
    # (c) 計算超額報酬率
    excess_return = annualized_return - risk_free_rate
    
    # 2. 計算夏普值
    sharpe_ratio = excess_return / annualized_std
    
    return sharpe_ratio

# --- 使用範例 ---

# 假設你的 DataFrame 叫做 stock_df，且已載入 GOOG 的五年資料
# stock_df = db_manager.get_stock("GOOG", "5y") 

# 假設當前的無風險利率為 3%
# risk_free_rate = 0.03

# # 計算 GOOG 的五年夏普值
# if not stock_df.empty:
#     goog_sharpe_ratio = calculate_sharpe_ratio(stock_df['Close'], risk_free_rate)
#     print(f"GOOG 的五年夏普值為: {goog_sharpe_ratio:.2f}")
# else:
#     print("資料為空，無法計算夏普值。")