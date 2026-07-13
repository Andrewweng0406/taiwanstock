"""
twse_data.py — 台灣證券交易所（TWSE）公開資料撈取與清洗
==========================================================
負責跟證交所的免費公開資料源打交道：抓資料、把奇怪格式（民國年日期、
千分位逗號字串、"-" 代表空值）清洗成乾淨的 pandas DataFrame。

跟 FinMind 不同，這幾支端點完全免費、不用 token、沒有額度限制，而且
「一次呼叫就能拿到全市場資料」，缺點是格式比較原始，要自己清洗。

用途分工（詳見 main.py 開頭的架構說明）：
- 即時掃描（run_full_scan）：全部改用這個檔案的函式，一次真的掃全市場
- 回測（run_backtest）：繼續用 FinMind，因為這裡的端點只能「逐日」查
  歷史某一天的全市場快照，不支援「單一股票、任意長度區間」查詢，
  拿來做長期回測反而要打更多次請求
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
REQUEST_DELAY_SECONDS = 0.2  # 對證交所也保持禮貌，不要瞬間連續狂打
USER_AGENT = "Mozilla/5.0"  # 部分舊版端點沒有帶 User-Agent 會回傳異常內容
RETRY_ATTEMPTS = 3  # 舊版端點偶爾會回傳暫時性 5xx，重試通常就會過（實測見 tpex_data.py）
RETRY_BACKOFF_SECONDS = 1.5  # 每次重試間隔遞增（1.5s, 3s），給對方伺服器喘息時間

# 只保留這種格式的證券代號：4 碼數字、不以 0 開頭。
# 用意是把 ETF（0050、00940、00400A...）、權證等其他有價證券排除掉，
# 只留「一般個股」，符合「選股」的原始需求（不是選 ETF）。
STOCK_ID_PATTERN = re.compile(r"^[1-9]\d{3}$")


def _clean_number(value) -> Optional[float]:
    """把「12,345」「--」「」這種證交所常見的字串數字清成 float，清不出來就回 None。"""
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
    統一的 TWSE 請求函式。任何失敗都只記錄 log、回傳 None，不會讓呼叫端當機。

    5xx（伺服器端暫時性問題）會重試最多 RETRY_ATTEMPTS 次；4xx（我們請求本身
    有問題，例如參數錯）重試沒有意義，直接放棄。逾時、連線中斷這類沒有明確
    狀態碼的錯誤也一併重試。跟 tpex_data.py 用同一套邏輯，那邊已經實測過
    TPEx 的舊版端點偶爾會回傳暫時性 520，這裡先一起補上，避免哪天 TWSE
    也遇到一樣的狀況。
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
                logger.error(f"[TWSE] 呼叫 {url} 回傳 {status}（用戶端錯誤，不重試）：{e}")
                break
            logger.warning(f"[TWSE] 呼叫 {url} 發生 {status} 錯誤，第 {attempt}/{RETRY_ATTEMPTS} 次嘗試：{e}")
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"[TWSE] 呼叫 {url} 發生連線錯誤，第 {attempt}/{RETRY_ATTEMPTS} 次嘗試：{e}")
        except ValueError as e:
            logger.error(f"[TWSE] 解析 {url} 回傳的 JSON 失敗：{e}")
            return None
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.error(f"[TWSE] 呼叫 {url} 重試 {RETRY_ATTEMPTS} 次後仍失敗，放棄這筆：{last_error}")
    return None


# ======================================================================
# 技術面：全市場每日收盤行情（開高低收 / 成交股數 / 本益比）
# ======================================================================
def fetch_daily_market_ohlc(target_date: date) -> pd.DataFrame:
    """
    抓「單一交易日」全市場每日收盤行情。

    用的是證交所傳統的 MI_INDEX 端點（不是新版 openapi.twse.com.tw），
    因為新版的 STOCK_DAY_ALL 只給「今天」，不支援查歷史某一天；
    這個舊端點反而支援 date 參數查任意過去的交易日，且已用真實請求驗證過。
    非交易日（假日）會回傳空結果，這裡回傳空 DataFrame，呼叫端自行跳過即可。

    回傳欄位（刻意對齊 FinMind TaiwanStockPrice 的命名，方便共用後續 pandas 邏輯）：
    stock_id / stock_name / date / open / max / min / close / Trading_Volume / PER
    """
    date_str = target_date.strftime("%Y%m%d")
    payload = _get_json(
        "https://www.twse.com.tw/exchangeReport/MI_INDEX",
        {"response": "json", "date": date_str, "type": "ALLBUT0999"},
    )
    if not payload or payload.get("stat") != "OK":
        return pd.DataFrame()

    target_table = None
    for table in payload.get("tables", []):
        if "每日收盤行情" in (table.get("title") or ""):
            target_table = table
            break
    if not target_table or not target_table.get("data"):
        return pd.DataFrame()

    rows = []
    for row in target_table["data"]:
        stock_id = row[0].strip()
        if not STOCK_ID_PATTERN.match(stock_id):
            continue  # 只留一般個股，排除 ETF / 權證
        rows.append(
            {
                "stock_id": stock_id,
                "stock_name": row[1].strip(),
                "date": target_date.isoformat(),
                "Trading_Volume": _clean_number(row[2]),
                "open": _clean_number(row[5]),
                "max": _clean_number(row[6]),
                "min": _clean_number(row[7]),
                "close": _clean_number(row[8]),
                "PER": _clean_number(row[15]) if len(row) > 15 else None,
            }
        )
    return pd.DataFrame(rows)


def fetch_market_ohlc_history(lookback_calendar_days: int = 40) -> pd.DataFrame:
    """
    逐日呼叫 fetch_daily_market_ohlc()，組出全市場最近 N 個「日曆天」的歷史行情，
    用來算 5MA / 20MA / 20 日均量。非交易日會自動被跳過（回傳空結果，不會混進來）。
    40 個日曆天通常能湊到至少 25-27 個交易日，足夠算 20MA。
    """
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
# 籌碼面：全市場三大法人買賣超（只取投信）
# ======================================================================
def fetch_daily_institutional(target_date: date) -> pd.DataFrame:
    """
    抓「單一交易日」全市場三大法人買賣超，只取投信（Investment Trust）淨買賣超股數。

    用的是 T86 端點——它沒有列在官方 openapi.twse.com.tw 的 Swagger 文件裡，
    是坊間長期在用、已用真實請求驗證過目前仍穩定可用的舊版端點。如果哪天
    證交所調整格式，這裡的欄位名稱查找（fields.index(...)）會拋例外，
    上層會記錄 log 並跳過那一天，不會讓整個掃描當機。
    """
    date_str = target_date.strftime("%Y%m%d")
    payload = _get_json(
        "https://www.twse.com.tw/rwd/zh/fund/T86",
        {"response": "json", "date": date_str, "selectType": "ALL"},
    )
    if not payload or payload.get("stat") != "OK" or not payload.get("data"):
        return pd.DataFrame()

    fields = payload.get("fields", [])
    try:
        idx_id = fields.index("證券代號")
        idx_net = fields.index("投信買賣超股數")
    except ValueError:
        logger.warning(f"[TWSE] T86（{date_str}）欄位格式跟預期不符，已跳過這天")
        return pd.DataFrame()

    rows = []
    for row in payload["data"]:
        stock_id = row[idx_id].strip()
        if not STOCK_ID_PATTERN.match(stock_id):
            continue
        net_buy = _clean_number(row[idx_net])
        if net_buy is None:
            continue
        rows.append({"stock_id": stock_id, "date": target_date.isoformat(), "net_buy": net_buy})
    return pd.DataFrame(rows)


def fetch_institutional_history(lookback_calendar_days: int = 15) -> pd.DataFrame:
    """逐日呼叫 fetch_daily_institutional()，組出最近 N 個日曆天的投信買賣超歷史。"""
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
# 基本面：全市場月營收年增率 + 股本（實收資本額）
# ======================================================================
def fetch_revenue_yoy_all() -> pd.DataFrame:
    """
    抓全市場最新一期上市公司月營收。這支資料集自己就已經算好年增率
    （欄位「營業收入-去年同月增減(%)」），不用像 FinMind 那樣自己抓歷史再手動算。
    """
    data = _get_json("https://openapi.twse.com.tw/v1/opendata/t187ap05_L", {})
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
    抓全市場上市公司基本資料，取「實收資本額」（單位：元，真正的股本數字）
    跟「已發行普通股數」（真正的在外流通股數，可以拿來算精確市值，不用再
    用股本除面額去估算）。
    """
    data = _get_json("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", {})
    if not data:
        return pd.DataFrame()

    rows = []
    for item in data:
        stock_id = str(item.get("公司代號", "")).strip()
        if not STOCK_ID_PATTERN.match(stock_id):
            continue
        capital = _clean_number(item.get("實收資本額"))
        if capital is None:
            continue
        shares_outstanding = _clean_number(item.get("已發行普通股數或TDR原股發行股數"))
        rows.append({"stock_id": stock_id, "capital": capital, "shares_outstanding": shares_outstanding})
    return pd.DataFrame(rows)
