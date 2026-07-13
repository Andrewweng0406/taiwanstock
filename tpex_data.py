"""
tpex_data.py — 證券櫃檯買賣中心（TPEx，上櫃）公開資料撈取與清洗
=====================================================================
跟 twse_data.py 是同一套分工邏輯，只是換一個免費資料源，補上「上櫃」
（TPEx）這塊 twse_data.py 沒有涵蓋的市場。用途、限制、清洗邏輯的理由
都跟 twse_data.py 完全一樣，這裡不重複解釋，只記錄 TPEx 特有的差異：

- 日期格式是民國年「斜線格式」（例如 "115/07/09"），不是 TWSE 那種
  「無斜線格式」（"20260709"），已經在 _to_roc_slash_date() 處理掉。
- 三大法人買賣明細那支舊版端點，JSON 的 fields 欄位名稱是重複的
  （六組「買進股數/賣出股數/買賣超股數」但文字都一樣，沒有標明是哪一類
  法人），沒辦法像 TWSE T86 那樣用欄位名稱查表。這裡改用「已知欄位順序」
  的固定索引（INSTITUTIONAL_NET_BUY_INDEX 等常數），順序已經用一檔真實
  股票（合晶 6182）的淨買超股數跟另一支「投信買賣超彙總表」端點的已知
  正確答案互相比對驗證過，如果 TPEx 哪天調整報表欄位順序，這裡要重新驗證。

回傳的 DataFrame 欄位名稱刻意跟 twse_data.py 對齊（stock_id / stock_name /
date / open / max / min / close / Trading_Volume / net_buy / capital /
revenue_growth_yoy），main.py 才能直接把兩邊的 DataFrame pd.concat 在一起，
不用另外寫一層欄位轉換。
"""

import logging
import re
import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger("taiwan_stock_scanner")

REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 0.2
USER_AGENT = "Mozilla/5.0"
RETRY_ATTEMPTS = 3  # 實測 TPEx 舊版端點偶爾會回傳暫時性 520，重試通常就會過
RETRY_BACKOFF_SECONDS = 1.5  # 每次重試間隔遞增（1.5s, 3s），給對方伺服器喘息時間

# 只保留 4 碼數字、不以 0 開頭的證券代號，排除 ETF／債券 ETF／權證。
STOCK_ID_PATTERN = re.compile(r"^[1-9]\d{3}$")

# 三大法人買賣明細報表（3itrade_hedge_result.php）的欄位是「位置」而非「名稱」
# 決定意義，這是已驗證過的欄位順序：
#   0=代號 1=名稱
#   2-4   = 外資及陸資（買進/賣出/買賣超）
#   5-7   = 外資自營商
#   8-10  = 外資合計
#   11-13 = 投信              ← 我們要的欄位
#   14-16 = 自營商（自行買賣）
#   17-19 = 自營商（避險）
#   20-22 = 自營商合計
#   23    = 三大法人買賣超股數合計
INSTITUTIONAL_NET_BUY_INDEX = 13


def _to_roc_slash_date(target_date: date) -> str:
    """TPEx 舊版端點用的民國年斜線格式，例如 2026-07-09 -> "115/07/09"。"""
    roc_year = target_date.year - 1911
    return f"{roc_year}/{target_date.month:02d}/{target_date.day:02d}"


def _clean_number(value) -> Optional[float]:
    """把「12,345」「--」「」這種常見的字串數字清成 float，清不出來就回 None。"""
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in ("", "-", "--", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _get_json(url: str, params: dict) -> Optional[dict]:
    """
    統一的 TPEx 請求函式。任何失敗都只記錄 log、回傳 None，不會讓呼叫端當機。

    實測掃描時 TPEx 舊版端點偶爾會回傳暫時性的 520（對方伺服器問題，不是我們
    請求格式錯），這種通常隔幾秒重試就會過。5xx（伺服器端問題）會重試最多
    RETRY_ATTEMPTS 次；4xx（我們請求本身有問題，例如參數錯）重試沒有意義，
    直接放棄。逾時、連線中斷這類沒有明確狀態碼的錯誤也一併重試。
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            last_error = e
            status = e.response.status_code if e.response is not None else None
            if status is not None and 400 <= status < 500:
                logger.error(f"[TPEx] 呼叫 {url} 回傳 {status}（用戶端錯誤，不重試）：{e}")
                break
            logger.warning(f"[TPEx] 呼叫 {url} 發生 {status} 錯誤，第 {attempt}/{RETRY_ATTEMPTS} 次嘗試：{e}")
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"[TPEx] 呼叫 {url} 發生連線錯誤，第 {attempt}/{RETRY_ATTEMPTS} 次嘗試：{e}")
        except ValueError as e:
            logger.error(f"[TPEx] 解析 {url} 回傳的 JSON 失敗：{e}")
            return None
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.error(f"[TPEx] 呼叫 {url} 重試 {RETRY_ATTEMPTS} 次後仍失敗，放棄這筆：{last_error}")
    return None


# ======================================================================
# 技術面：上櫃全市場每日收盤行情
# ======================================================================
def fetch_daily_market_ohlc(target_date: date) -> pd.DataFrame:
    """
    抓「單一交易日」上櫃全市場每日收盤行情。非交易日回傳空 DataFrame。
    欄位命名刻意對齊 twse_data.fetch_daily_market_ohlc()，方便直接 pd.concat。
    """
    payload = _get_json(
        "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php",
        {"l": "zh-tw", "d": _to_roc_slash_date(target_date), "se": "EW", "o": "json"},
    )
    if not payload or payload.get("stat") != "ok" or not payload.get("tables"):
        return pd.DataFrame()

    rows_data = payload["tables"][0].get("data") or []
    rows = []
    for row in rows_data:
        stock_id = row[0].strip()
        if not STOCK_ID_PATTERN.match(stock_id):
            continue  # 只留一般個股，排除 ETF / 債券 ETF / 權證
        rows.append(
            {
                "stock_id": stock_id,
                "stock_name": row[1].strip(),
                "date": target_date.isoformat(),
                "Trading_Volume": _clean_number(row[7]),
                "open": _clean_number(row[4]),
                "max": _clean_number(row[5]),
                "min": _clean_number(row[6]),
                "close": _clean_number(row[2]),
                "PER": None,  # TPEx 這支端點沒有本益比欄位
            }
        )
    return pd.DataFrame(rows)


def fetch_market_ohlc_history(lookback_calendar_days: int = 40) -> pd.DataFrame:
    """逐日呼叫 fetch_daily_market_ohlc()，組出上櫃全市場最近 N 個日曆天的歷史行情。"""
    frames = []
    end_date = date.today()
    for offset in range(lookback_calendar_days):
        target_date = end_date - timedelta(days=offset)
        df = fetch_daily_market_ohlc(target_date)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ======================================================================
# 籌碼面：上櫃全市場三大法人買賣超（只取投信）
# ======================================================================
def fetch_daily_institutional(target_date: date) -> pd.DataFrame:
    """
    抓「單一交易日」上櫃全市場投信買賣超。非交易日回傳空 DataFrame。
    這支舊版報表欄位名稱重複，用固定位置索引取值，見檔案開頭說明。
    """
    payload = _get_json(
        "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php",
        {"l": "zh-tw", "se": "EW", "t": "D", "d": _to_roc_slash_date(target_date), "o": "json"},
    )
    if not payload or payload.get("stat") != "ok" or not payload.get("tables"):
        return pd.DataFrame()

    rows_data = payload["tables"][0].get("data") or []
    rows = []
    for row in rows_data:
        stock_id = row[0].strip()
        if not STOCK_ID_PATTERN.match(stock_id):
            continue
        if len(row) <= INSTITUTIONAL_NET_BUY_INDEX:
            continue  # 欄位數不如預期，跳過這筆，避免用錯位置的資料
        net_buy = _clean_number(row[INSTITUTIONAL_NET_BUY_INDEX])
        if net_buy is None:
            continue
        rows.append({"stock_id": stock_id, "date": target_date.isoformat(), "net_buy": net_buy})
    return pd.DataFrame(rows)


def fetch_institutional_history(lookback_calendar_days: int = 15) -> pd.DataFrame:
    """逐日呼叫 fetch_daily_institutional()，組出最近 N 個日曆天的上櫃投信買賣超歷史。"""
    frames = []
    end_date = date.today()
    for offset in range(lookback_calendar_days):
        target_date = end_date - timedelta(days=offset)
        df = fetch_daily_institutional(target_date)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ======================================================================
# 基本面：上櫃全市場月營收年增率 + 股本
# ======================================================================
def fetch_revenue_yoy_all() -> pd.DataFrame:
    """抓全市場最新一期上櫃公司月營收，這支資料集本身就已經算好年增率。"""
    data = _get_json("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O", {})
    if not data:
        return pd.DataFrame()

    rows = []
    for item in data:
        stock_id = str(item.get("公司代號", "")).strip()
        if not STOCK_ID_PATTERN.match(stock_id):
            continue
        yoy = _clean_number(item.get("營業收入-去年同月增減(%)"))
        if yoy is None:
            continue
        rows.append(
            {
                "stock_id": stock_id,
                "stock_name": str(item.get("公司名稱", "")).strip(),
                "revenue_growth_yoy": yoy,
            }
        )
    return pd.DataFrame(rows)


def fetch_capital_all() -> pd.DataFrame:
    """
    抓全市場上櫃公司基本資料，取實收資本額（單位：元）跟「已發行股數」
    （IssueShares，真正的在外流通股數，可以拿來算精確市值）。
    """
    data = _get_json("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", {})
    if not data:
        return pd.DataFrame()

    rows = []
    for item in data:
        stock_id = str(item.get("SecuritiesCompanyCode", "")).strip()
        if not STOCK_ID_PATTERN.match(stock_id):
            continue
        capital = _clean_number(item.get("Paidin.Capital.NTDollars"))
        if capital is None:
            continue
        shares_outstanding = _clean_number(item.get("IssueShares"))
        rows.append({"stock_id": stock_id, "capital": capital, "shares_outstanding": shares_outstanding})
    return pd.DataFrame(rows)
