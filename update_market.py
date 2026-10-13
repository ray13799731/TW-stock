import json
import random
import os
import requests
import pandas as pd
from datetime import datetime

def fetch_twse_quotes():
    """抓取證交所全市場上市行情"""
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    stocks = {}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        data = res.json()
        
        # 尋找包含收盤行情的表格 (通常是 data9 或 tables 中的某一組)
        rows = None
        if 'data9' in data:
            rows = data['data9']
        elif 'tables' in data:
            for t in data['tables']:
                if '每日收盤行情' in t.get('title', ''):
                    rows = t.get('data', [])
                    break
        
        if rows:
            for row in rows:
                code = str(row[0]).strip()
                name = str(row[1]).strip()
                # 濾除權證與特殊代號，只留 4 碼普通股
                if len(code) != 4 or not code.isdigit():
                    continue
                
                # 成交股數轉張數
                try:
                    vol_shares = int(str(row[2]).replace(',', ''))
                    yesterday_vol = vol_shares // 1000
                except:
                    yesterday_vol = 0
                
                # 收盤價
                try:
                    price = float(str(row[8]).replace(',', ''))
                except:
                    price = 0.0

                stocks[code] = {
                    'code': code,
                    'name': name,
                    'market': '上市',
                    'yesterdayVol': yesterday_vol,
                    'price': price
                }
    except Exception as e:
        print(f"TWSE 抓取異常: {e}")
    return stocks

def main():
    print("開始執行全市場資料處理...")
    quotes = fetch_twse_quotes()
    
    # 防呆：如果 API 剛好在非交易日或維護中回傳空值，保留原先檔案避免變成 0 檔
    if not quotes and os.path.exists("market_stocks.json"):
        print("警告：本次未抓取到有效行情，保留既有檔案。")
        return

    output = []
    for code, item in quotes.items():
        yesterday_vol = item['yesterdayVol']
        # 模擬 20 日均量與籌碼狀態計算
        if random.random() < 0.15:
            vol_ratio = round(random.uniform(1.5, 3.2), 2)
            ma20_vol = max(500, int(yesterday_vol / vol_ratio))
        else:
            vol_ratio = round(random.uniform(0.6, 1.3), 2)
            ma20_vol = max(500, int(yesterday_vol / vol_ratio))

        output.append({
            "code": item['code'],
            "name": item['name'],
            "market": item['market'],
            "price": item['price'],
            "yesterdayVol": yesterday_vol,
            "ma20Vol": ma20_vol,
            "volumeRatio": vol_ratio,
            "trustStreak": 6 if (item['price'] > 40 and vol_ratio >= 1.2) else 1,
            "bigHolderStreak": 4 if vol_ratio >= 1.2 else 1,
            "retailStreak": 4 if vol_ratio >= 1.2 else 1,
            "shareholderDiff": -280 if vol_ratio >= 1.2 else 90,
            "brokerDiff": -35 if vol_ratio >= 1.2 else 15,
            "trapForeignSell": False,
            "trapLargeIndexArbitrage": (code in ['2330', '2317']),
            "trapDealerHedgeSpike": False
        })

    print(f"成功處理 {len(output)} 檔個股，準備寫入 market_stocks.json...")
    with open("market_stocks.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("寫入完成！")

if __name__ == "__main__":
    main()
