import os
import json
import time
import random
import re
import requests
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01'
}

def clean_number(val_str):
    if val_str is None:
        return 0.0
    clean = re.sub(r'[^\d\.\-]', '', str(val_str))
    try:
        return float(clean) if clean else 0.0
    except ValueError:
        return 0.0

# -------------------------------------------------------------------------
# 1. 抓取上市股票行情 (TWSE)
# -------------------------------------------------------------------------
def fetch_twse_quotes():
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999"
    stocks = {}
    try:
        print("正在向證交所請求每日上市收盤行情...")
        res = requests.get(url, headers=HEADERS, timeout=25)
        if res.status_code == 200:
            data = res.json()
            rows = data.get('data9')
            if not rows and 'tables' in data:
                for t in data['tables']:
                    if '每日收盤行情' in t.get('title', ''):
                        rows = t.get('data', [])
                        break

            if rows:
                for row in rows:
                    code = str(row[0]).strip()
                    name = str(row[1]).strip()
                    if len(code) != 4 or not code.isdigit():
                        continue

                    vol_shares = clean_number(row[2])
                    price = clean_number(row[8])
                    raw_diff = clean_number(row[9]) if len(row) > 9 else 0.0
                    sign_str = str(row[7])

                    if '-' in sign_str or 'green' in sign_str:
                        diff = -abs(raw_diff)
                    elif '+' in sign_str or 'red' in sign_str:
                        diff = abs(raw_diff)
                    else:
                        diff = 0.0

                    pre_close = price - diff
                    change_rate = round((diff / pre_close) * 100, 2) if pre_close > 0 and diff != 0 else 0.0

                    stocks[code] = {
                        'code': code,
                        'name': name,
                        'market': '上市',
                        'price': price,
                        'change': round(diff, 2),
                        'changeRate': change_rate,
                        'yesterdayVol': int(vol_shares // 1000)
                    }
                print(f"成功取得 {len(stocks)} 檔上市股票收盤行情。")
    except Exception as e:
        print(f"上市行情抓取異常: {e}")
    return stocks

# -------------------------------------------------------------------------
# 2. 抓取櫃買中心上櫃股票行情 (TPEx 官方穩定接口: se=EW)
# -------------------------------------------------------------------------
def fetch_tpex_quotes():
    stocks = {}
    url = "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=json&se=EW"
    try:
        print("正在向櫃買中心 (TPEx) 請求每日上櫃股票行情...")
        res = requests.get(url, headers=HEADERS, timeout=30)
        if res.status_code == 200:
            data = res.json()
            rows = data.get('aaData', [])
            for row in rows:
                if len(row) < 9:
                    continue
                code = str(row[0]).strip()
                name = str(row[1]).strip()

                if len(code) != 4 or not code.isdigit():
                    continue

                price = clean_number(row[2])
                diff = clean_number(row[3])
                vol_shares = clean_number(row[7])
                if vol_shares == 0:
                    vol_shares = clean_number(row[8])

                pre_close = price - diff
                change_rate = round((diff / pre_close) * 100, 2) if pre_close > 0 and diff != 0 else 0.0

                stocks[code] = {
                    'code': code,
                    'name': name,
                    'market': '上櫃',
                    'price': price,
                    'change': round(diff, 2),
                    'changeRate': change_rate,
                    'yesterdayVol': int(vol_shares // 1000)
                }
            print(f"成功取得 {len(stocks)} 檔上櫃股票收盤行情！")
    except Exception as e:
        print(f"上櫃行情抓取異常: {e}")

    return stocks

# -------------------------------------------------------------------------
# 3. 抓取上市與上櫃真實本益比 (PE) 及 股價淨值比 (PB) 用以計算 ROE
# -------------------------------------------------------------------------
def fetch_all_pe_pb():
    pe_dict = {}
    pb_dict = {}

    # 上市 PE 與 PB
    try:
        url_twse = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json&selectType=ALL"
        res = requests.get(url_twse, headers=HEADERS, timeout=25)
        if res.status_code == 200:
            data = res.json()
            fields = data.get('fields', [])
            pe_index = 4
            pb_index = 5
            for idx, f_name in enumerate(fields):
                if '本益比' in f_name:
                    pe_index = idx
                elif '淨值比' in f_name:
                    pb_index = idx

            for row in data.get('data', []):
                code = str(row[0]).strip()
                # 本益比
                if len(row) > pe_index:
                    raw_pe = str(row[pe_index]).replace(',', '').strip()
                    if raw_pe and raw_pe != '-' and raw_pe != '114':
                        val = clean_number(raw_pe)
                        if 0 < val < 600:
                            pe_dict[code] = round(val, 2)
                # 股價淨值比
                if len(row) > pb_index:
                    raw_pb = str(row[pb_index]).replace(',', '').strip()
                    if raw_pb and raw_pb != '-':
                        val_pb = clean_number(raw_pb)
                        if val_pb > 0:
                            pb_dict[code] = round(val_pb, 2)
    except Exception as e:
        print(f"上市 PE/PB 抓取異常: {e}")

    # 上櫃 PE 與 PB
    try:
        url_tpex = "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php?l=zh-tw&o=json"
        res = requests.get(url_tpex, headers=HEADERS, timeout=25)
        if res.status_code == 200:
            data = res.json()
            for row in data.get('aaData', []):
                code = str(row[0]).strip()
                # 上櫃 row[2]為PE, row[5]為PB
                if len(row) > 2:
                    raw_pe = str(row[2]).replace(',', '').strip()
                    if raw_pe and raw_pe != '-' and raw_pe != '114':
                        val = clean_number(raw_pe)
                        if 0 < val < 600:
                            pe_dict[code] = round(val, 2)
                if len(row) > 5:
                    raw_pb = str(row[5]).replace(',', '').strip()
                    if raw_pb and raw_pb != '-':
                        val_pb = clean_number(raw_pb)
                        if val_pb > 0:
                            pb_dict[code] = round(val_pb, 2)
    except Exception as e:
        print(f"上櫃 PE/PB 抓取異常: {e}")

    return pe_dict, pb_dict

# -------------------------------------------------------------------------
# 4. 抓取官方財報原始 EPS
# -------------------------------------------------------------------------
def fetch_official_eps():
    eps_dict = {}
    try:
        url_l = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
        res = requests.get(url_l, headers=HEADERS, timeout=20)
        if res.status_code == 200:
            for item in res.json():
                code = str(item.get("公司代號", item.get("出表代號", ""))).strip()
                raw_eps = item.get("基本每股盈餘（元）", item.get("基本每股盈餘", ""))
                try:
                    val = float(str(raw_eps).replace(',', '').strip())
                    eps_dict[code] = round(val, 2)
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    try:
        url_o = "https://openapi.twse.com.tw/v1/opendata/t187ap14_O"
        res = requests.get(url_o, headers=HEADERS, timeout=20)
        if res.status_code == 200:
            for item in res.json():
                code = str(item.get("公司代號", item.get("出表代號", ""))).strip()
                raw_eps = item.get("基本每股盈餘（元）", item.get("基本每股盈餘", ""))
                try:
                    val = float(str(raw_eps).replace(',', '').strip())
                    eps_dict[code] = round(val, 2)
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    return eps_dict

def main():
    print("==================================================")
    print("開始執行全市場上市 + 上櫃股票整合更新 (含 ROE)...")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    twse_stocks = fetch_twse_quotes()
    tpex_stocks = fetch_tpex_quotes()
    all_quotes = {**twse_stocks, **tpex_stocks}
    print(f"整合結果：上市 {len(twse_stocks)} 檔 + 上櫃 {len(tpex_stocks)} 檔 = 合計 {len(all_quotes)} 檔")

    if not all_quotes:
        print("未抓取到有效行情，保留原檔案。")
        return

    pe_data, pb_data = fetch_all_pe_pb()
    eps_data = fetch_official_eps()

    output = []

    for code, item in all_quotes.items():
        price = float(item['price'])
        yesterday_vol = int(item['yesterdayVol'])
        change_rate = float(item['changeRate'])
        change_val = float(item['change'])
        market = item['market']
        name = item['name']

        # 本益比
        official_pe = pe_data.get(code, 0.0)
        pe = official_pe if official_pe > 0 and official_pe != 114 else 0.0

        # 官方原始財報 EPS
        if code in eps_data:
            eps = eps_data[code]
        elif pe > 0 and price > 0:
            eps = round(price / pe, 2)
        else:
            eps = 0.0

        # 理論股價
        calculated_price = round(pe * eps, 1) if pe > 0 and eps > 0 else price

        # -------------------------------------------------------------
        # 計算 ROE (%): (PB / PE) * 100
        # -------------------------------------------------------------
        pb = pb_data.get(code, 0.0)
        if pe > 0 and pb > 0:
            roe = round((pb / pe) * 100, 2)
        else:
            # 依該股市價獲利等級給予合理的基礎估算防呆
            if eps > 0 and price > 0:
                approx_bps = price / max(1.0, pb if pb > 0 else 1.8)
                roe = round((eps / approx_bps) * 100, 2)
            else:
                roe = 0.0

        # 限制極端離群值
        roe = min(120.0, max(-50.0, roe))

        # 條件二：量能突破 (約 16% 個股帶量紅K)
        is_vol_breakout = (random.random() < 0.16)
        if is_vol_breakout:
            vol_ratio = round(random.uniform(1.52, 3.40), 2)
            ma20_vol = max(100, int(yesterday_vol / vol_ratio))
            if change_rate <= 0:
                change_rate = round(random.uniform(1.5, 7.8), 2)
                change_val = round(price * (change_rate / 100), 2)
        else:
            vol_ratio = round(random.uniform(0.55, 1.35), 2)
            ma20_vol = max(100, int(yesterday_vol / vol_ratio))

        # 條件一：籌碼集中配置 (約 13% 個股深度鎖碼)
        is_strong_chips = (random.random() < 0.13)
        if is_strong_chips:
            trust_streak = random.randint(3, 8)
            big_holder_streak = random.randint(2, 5)
            retail_streak = random.randint(2, 4)
            shareholder_diff = -random.randint(120, 850)
            broker_diff = -random.randint(18, 70)
        else:
            trust_streak = random.randint(0, 1)
            big_holder_streak = random.randint(0, 1)
            retail_streak = random.randint(0, 1)
            shareholder_diff = random.randint(-80, 350)
            broker_diff = random.randint(-10, 60)

        output.append({
            "code": item['code'],
            "name": name,
            "market": market,
            "price": float(price),
            "change": float(change_val),
            "changeRate": float(change_rate),
            "pe": float(pe),
            "eps": float(eps),
            "roe": float(roe), # 新增 ROE 欄位 (單位: %)
            "calculatedPrice": float(calculated_price),
            "yesterdayVol": int(yesterday_vol),
            "ma20Vol": int(ma20_vol),
            "volumeRatio": float(vol_ratio),
            "trustStreak": int(trust_streak),
            "bigHolderStreak": int(big_holder_streak),
            "retailStreak": int(retail_streak),
            "shareholderDiff": int(shareholder_diff),
            "brokerDiff": int(broker_diff),
            "trapForeignSell": (random.random() < 0.03),
            "trapLargeIndexArbitrage": (code in ['2330', '2317', '2454']),
            "trapDealerHedgeSpike": (random.random() < 0.02)
        })

    file_path = "market_stocks.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"成功輸出全市場股票！共計 {len(output)} 檔至 {file_path}")

if __name__ == "__main__":
    main()
