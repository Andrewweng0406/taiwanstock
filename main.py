"""
main.py — 台股量化選股 App 後端
================================
架構：做法 B（前後端分離）。本檔案只負責後端 API，前端由 v0 產出的 React + Tailwind
頁面（frontend/ 目錄）透過 fetch(..., { method: "POST" }) 呼叫下方的路由。

核心路由：
- POST /api/scan          — 用「今天」的資料掃全市場，找出符合三大條件的股票
- POST /api/backtest      — 用「過去一年」的資料回頭驗證這套規則的勝率／平均報酬
  （不要只看 /api/scan 的結果就進場，那只代表「今天符合條件」，不代表「過去
  符合這個條件的股票比較容易漲」——後者才是 /api/backtest 在做的事）
- GET  /api/stock/{id}    — 查單一股票的完整詳情，股票比較／個股詳情頁用
- POST /api/chat          — AI 選股助理，把 /api/scan 的最新結果當背景資料回答問題
  （見 chat_assistant.py，OpenAI/Gemini 沒設定金鑰時會自動退回規則式回覆，
  不會因為還沒申請 LLM 金鑰就讓聊天功能整個打不開）

----------------------------------------------------------------------
【重要】兩個路由用兩種不同的資料來源，這是刻意的分工，不是技術債：

- /api/scan     → twse_data.py + tpex_data.py → 證交所（TWSE）+ 櫃買中心（TPEx）公開資料
- /api/backtest → _finmind_get() → FinMind REST API

為什麼要分兩套？因為兩邊各有各的強項，實測後刻意這樣分工：

1. TWSE + TPEx（用在即時掃描）：
   完全免費、不用 token、沒有額度上限，而且好幾支端點「一次呼叫就能拿到
   全市場資料」（例如全市場今日收盤價、全市場三大法人買賣超、全市場月營收
   年增率、全市場股本），所以 /api/scan 現在掃的是真正的全市場——上市
   （TWSE，約 1000 多檔）+ 上櫃（TPEx，約 800 多檔），加總約 1800 多檔，
   不再受限於一份固定觀察清單。
   缺點：格式很原始（民國年日期、千分位逗號字串、只能逐日查歷史，TPEx
   的三大法人報表欄位名稱還會重複），細節都封裝在 twse_data.py /
   tpex_data.py 裡清洗過了。技術面/籌碼面兩邊資料源用 ThreadPoolExecutor
   平行抓取，不用序列等待，掃描時間大約可以砍半。

2. FinMind（用在回測 + 個股詳情頁 /api/stock/{stock_id}）：
   欄位乾淨、支援「單一股票 + 任意長度日期區間」的彈性查詢，很適合回測
   需要的「一次拿一檔股票一整年資料」，也很適合單股查詢（幾次請求就好，
   不需要像全市場掃描那樣抓好幾天的整個市場資料）。缺點是免費版已經把
   「不帶 data_id 一次抓全市場」這個功能鎖給付費 Sponsor 會員了（實測
   回傳 400 "Your level is free..."），所以回測仍然限定在 WATCHLIST
   這份自訂清單（目前 100 檔，股本 < 40 億的中小型股，見下方 WATCHLIST
   定義處的說明），逐檔用 data_id 查詢。之後如果帳號升級 Sponsor，可以
   比照 TWSE/TPEx 的作法把回測也改成全市場。

3. 三大法人 name 欄位字串（FinMind）：
   投信的字串值為 "Investment_Trust"（已用真實 API 呼叫驗證過）。
----------------------------------------------------------------------

安裝方式：
    pip install fastapi uvicorn requests pandas python-dotenv
啟動方式：
    uvicorn main:app --reload --port 8000
（FinMind token 已存在同資料夾的 .env 檔，程式啟動時會自動讀取，不需要每次手動 export，
只有 /api/backtest 跟 /api/stock/{stock_id} 會用到這個 token；
/api/scan 走 TWSE + TPEx，完全不需要任何金鑰）

AI 選股助理（/api/chat）金鑰設定（非必要，兩個都不設定也能動，只是回覆
會退回規則式模板，不是真正的 AI，見 chat_assistant.py 開頭說明）：
    在 .env 加一行（擇一，OpenAI 優先）：
        OPENAI_API_KEY=sk-xxxxxxxx
        GEMINI_API_KEY=xxxxxxxx

"""

import json
import logging
import math
import os
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import chat_assistant
import taifex_data
import tpex_data
import twse_data

# 自動讀取同資料夾的 .env 檔（內容如 FINMIND_API_TOKEN=xxx），該檔已加進
# .gitignore，不會被誤傳到公開 repo。找不到 .env 也不會報錯，正常繼續執行。
load_dotenv()

# ======================================================================
# 1. 基本設定
# ======================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("taiwan_stock_scanner")

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"

# FinMind API Token：只從環境變數 FINMIND_API_TOKEN 讀取，程式碼裡不會寫死任何金鑰。
# 目前已存在同資料夾的 .env 檔（已加進 .gitignore，不會被誤傳到公開 repo），
# 上面的 load_dotenv() 會在程式啟動時自動載入，不需要每次手動 export。
# 【安全提醒】Token 等同你帳號的永久密碼，絕對不要把 .env 內容貼到截圖、聊天群組
# 或公開 repo；如果不小心外流了，去 FinMind 網站按「更新 token」重新產生一組即可。
# 有填 token：600 次/小時；沒填：300 次/小時。本程式一次回測的請求數 ≈
# len(WATCHLIST) × 4 + 1（股價/法人/營收/股本各一次，外加一次股票名稱查詢），
# 請視清單大小評估是否需要 token。
API_TOKEN: str = os.getenv("FINMIND_API_TOKEN", "")

REQUEST_TIMEOUT = 30  # 單次 HTTP 請求逾時秒數
REQUEST_DELAY_SECONDS = 0.15  # 每次 FinMind API 呼叫之間的間隔，避免瞬間灌爆流量
INVESTMENT_TRUST_NAME = "Investment_Trust"  # FinMind 三大法人資料集中「投信」的 name 欄位值

# 掃描結果的本地快取檔案。同一個日曆天內第一次成功掃描後就會寫進這裡，
# 之後同一天內的請求直接讀檔秒回，不用重新對 TWSE/TPEx 發出上百次請求。
# 這個檔案是執行期產生的資料、不是原始碼，已加進 .gitignore。
SCAN_CACHE_FILE = Path(__file__).parent / "latest_scan_result.json"

# 三大生態選股的門檻常數。即時掃描（run_full_scan，資料來源 TWSE）跟回測
# （run_backtest，資料來源 FinMind）共用這幾個常數，確保回測驗證的是「跟即時
# 掃描完全相同的規則」，而不是兩套邏輯各自為政、回測結果對不上實際掃描行為。
VOLUME_MULTIPLIER_THRESHOLD = 1.5  # 今日成交量 > 20日均量 的幾倍
# 2026-07-13：原本是 2 倍。用 100 檔中小型股清單（見下方 WATCHLIST）做五年回測
# 比較「2 倍 vs 1.5 倍」後，1.5 倍讓訊號數幾乎翻倍（399→795），但 20 日勝率
# 只掉 0.5 個百分點（56.5%→56.0%），平均報酬/獲利因子沒有變差，是六種放寬
# 情境裡風險最低的調整，因此正式採用。詳細比較見 backtest_relaxation_analysis.py
# 的研究方法（本檔不依賴它，只是同一套四條件計算邏輯的參數來源）。
INSTITUTIONAL_STREAK_DAYS = 3  # 投信連續買超天數門檻
REVENUE_YOY_THRESHOLD = 20  # 營收年增率門檻（%）
CAPITAL_LIMIT = 4_000_000_000  # 股本門檻：40 億元（即時掃描用 TWSE/TPEx 的真實「實收資本額」）

# 自訂觀察清單：只有 /api/backtest（回測）還在用這份清單。/api/scan（即時掃描）
# 已經改用 TWSE 資料源，掃的是真正的全市場，不再受這份清單限制。
# 回測沒有跟進全市場，是因為 FinMind 免費版的「單一股票 + 任意區間」查詢很好用，
# 但沒有全市場批次下載，逐檔查全市場約 1700 檔的成本太高。
#
# 2026-07-13：改用「股本 < 40 億」+「流動性前 100」的中小型股清單，取代原本
# 61 檔大型權值股清單——原本的清單完全沒有貼合這個 App 主打中小型股的選股邏輯，
# 套用股本門檻後訊號數少到不能拿來下結論。這份清單的產生方式（build_small_cap_watchlist.py）：
# 1. 目前實收股本 < 40 億元、上市 + 上櫃普通股
# 2. 最近 20 個交易日至少 15 日有成交（濾掉停牌/極冷門股）
# 3. 依 20 日成交金額中位數排名取前 100 檔（第 100 名中位數約 10.08 億元/日，
#    確保回測模擬買賣時有基本流動性，不是紙上富貴）
# 用這份清單做五年回測，六種門檻情境的 20 日到期樣本都超過 30 筆（原始嚴格
# 條件 391 筆、最寬鬆情境 3272 筆），樣本數足以拿來比較，不再是個位數訊號的
# 大型股清單。原始清單來源、完整比較結果見 small_cap_watchlist.json /
# backtest_relaxation_analysis.py。
WATCHLIST: list[str] = [
    "3008", "8299", "2383", "3443", "3017", "6274", "6669", "3661", "6213", "3042",
    "3665", "6223", "2472", "5289", "8358", "2404", "2484", "3081", "7769", "6139",
    "6271", "3374", "3653", "2059", "3260", "5274", "6531", "6446", "3450", "8261",
    "6515", "6442", "2375", "4979", "6451", "3406", "3006", "2481", "8043", "6415",
    "5351", "5328", "3491", "8028", "3026", "3211", "3324", "3363", "6805", "6187",
    "8996", "3533", "1519", "4931", "3035", "6278", "2486", "6173", "3707", "5425",
    "3357", "3163", "6672", "6409", "3016", "2464", "3131", "4991", "3715", "2426",
    "2455", "5269", "6510", "6781", "3529", "2351", "2458", "6197", "6207", "8210",
    "8033", "6719", "6683", "6175", "3293", "6217", "5536", "3583", "3362", "4967",
    "3167", "8039", "3149", "6789", "6196", "5371", "3019", "6290", "4966", "8016",
]

app = FastAPI(
    title="台股量化選股 API",
    description="一鍵掃描全市場（TWSE 上市 + TPEx 上櫃）：技術面 + 籌碼面 + 基本面 三大生態選股，並可回測驗證勝率、查詢個股詳情",
)

# 2026-07-13：正式上線後才發現一直忘記把這裡從開發階段的 allow_origins=["*"]
# 收回來——開放所有來源代表任何網站都能讓使用者瀏覽器直接呼叫這支 API。
# 預設鎖定正式站前端網域 + 本機開發用的 localhost，可用 ALLOWED_ORIGINS
# 環境變數（逗號分隔）覆蓋，之後換網域/加自訂網域不用改程式碼重新部署。
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "https://frontend-production-6ee3.up.railway.app,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================================
# 2. 全局狀態鎖：避免前端重複點擊「一鍵掃描」/「執行回測」時，
#    後端同時跑好幾次這種會大量呼叫 FinMind 的重運算。
#    /api/scan 跟 /api/backtest 共用同一把鎖，兩者都很花時間、很花 API 額度，
#    不應該讓它們同時進行。
# ======================================================================
heavy_task_lock = threading.Lock()


# ======================================================================
# 2.5 簡單的每 IP 頻率限制：CORS 只擋得住瀏覽器發出的跨網域請求，擋不住
#    有人直接寫腳本打 API。/api/chat 每次呼叫都會燒 OpenAI/Gemini 額度、
#    /api/stock/{id} 每次都會燒 FinMind 額度，兩個都是「重複呼叫 = 直接
#    燒錢/燒額度」的端點，值得加這一層保護。
#
#    用記憶體內的固定視窗（fixed window）算，不需要額外的 Redis／資料庫，
#    現在只有單一 Railway instance，夠用；如果之後水平擴展成多個 instance，
#    要換成共用儲存才能跨 instance 一起算，不然每個 instance 會各自放行。
# ======================================================================
_rate_limit_lock = threading.Lock()
_rate_limit_history: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """優先用 Railway 等反向代理帶的 X-Forwarded-For，沒有才退回連線本身的 IP。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request, bucket: str, max_requests: int, window_seconds: int = 60) -> None:
    """超過頻率限制就直接丟 HTTP 429，讓呼叫端知道是被擋，不是伺服器出錯。"""
    key = f"{bucket}:{_client_ip(request)}"
    now = time.time()
    with _rate_limit_lock:
        history = _rate_limit_history[key]
        while history and now - history[0] > window_seconds:
            history.popleft()
        if len(history) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"請求太頻繁，請稍後再試（每 {window_seconds} 秒最多 {max_requests} 次）",
            )
        history.append(now)


# ======================================================================
# 3. FinMind 資料撈取共用函式
# ======================================================================
def _finmind_get(
    dataset: str,
    start_date: str,
    end_date: Optional[str] = None,
    data_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    單次 FinMind API 呼叫。任何失敗（連線逾時、JSON 格式異常、FinMind 回傳
    錯誤狀態…）都只記錄 log 並回傳空的 DataFrame，不會讓整個掃描流程當機。
    """
    params = {"dataset": dataset, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    if data_id:
        params["data_id"] = data_id

    headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}

    try:
        resp = requests.get(FINMIND_API_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("status") != 200:
            logger.warning(f"[FinMind] {dataset}({data_id}) 回傳非成功狀態：{payload.get('msg')}")
            return pd.DataFrame()

        return pd.DataFrame(payload.get("data", []))

    except requests.exceptions.RequestException as e:
        logger.error(f"[FinMind] 呼叫 {dataset}({data_id}) 發生連線錯誤：{e}")
        return pd.DataFrame()
    except ValueError as e:
        logger.error(f"[FinMind] 解析 {dataset}({data_id}) 回傳的 JSON 失敗：{e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"[FinMind] 撈取 {dataset}({data_id}) 發生未預期錯誤：{e}")
        return pd.DataFrame()
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)


def _json_safe(value):
    """
    遞迴把 NaN / Infinity / -Infinity 換成 None。

    pandas/numpy 的計算很容易產生這些值（例如除以零、0/0），但標準 JSON
    格式不允許這些值，FastAPI 預設用 Python 內建的 json.dumps 序列化回應，
    遇到就直接丟 ValueError、整支 API 回傳 500——不是「資料有點怪」而是
    「整支功能打不開」。所有要回傳給前端的 dict/list，最後都應該先過一次
    這個函式再回傳，才不會因為某一檔股票某一天剛好某個欄位算出 nan/inf，
    就讓一個原本 90% 都算好的結果整包回傳失敗。
    """
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


# ======================================================================
# 4. 技術面：5MA / 20MA / 量能倍數（全市場 = 上市 TWSE + 上櫃 TPEx）
# ======================================================================
def _fetch_market_ohlc_all_markets(lookback_calendar_days: int = 40) -> pd.DataFrame:
    """
    平行抓上市（TWSE）+ 上櫃（TPEx）的全市場歷史收盤行情並合併成一張表。
    兩邊資料來源互相獨立，用 ThreadPoolExecutor 平行呼叫，掃描時間大約可以
    砍半（不用先等上市抓完 40 天，才開始抓上櫃 40 天）。
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        twse_future = executor.submit(twse_data.fetch_market_ohlc_history, lookback_calendar_days)
        tpex_future = executor.submit(tpex_data.fetch_market_ohlc_history, lookback_calendar_days)
        twse_df = twse_future.result()
        tpex_df = tpex_future.result()
    return pd.concat([twse_df, tpex_df], ignore_index=True)


def analyze_technical_market():
    """
    技術面計算，範圍是全市場（上市 TWSE + 上櫃 TPEx，約 1800 多檔）。

    - _fetch_market_ohlc_all_markets() 平行抓兩邊最近 40 個日曆天的收盤行情
      並合併，40 天日曆天通常能湊到至少 25-27 個交易日，足夠算 20MA。
    - 在本地端用 pandas 對「每一檔股票」計算 5MA、20MA、20日均量。
    - 篩選條件：今日收盤價 > 5MA 且 > 20MA，且今日成交量 > 20日均量的
      VOLUME_MULTIPLIER_THRESHOLD 倍。

    回傳： (最新交易日字串 或 None, 篩選結果 DataFrame)
           篩選結果欄位已直接對齊前端需要的命名：
           stock_id / stock_name / current_price / stop_loss_price / volume_multiplier
    """
    df = _fetch_market_ohlc_all_markets(lookback_calendar_days=40)
    if df.empty:
        logger.warning("[技術面] 全市場股價資料為空，可能是連假或證交所/櫃買中心服務異常")
        return None, pd.DataFrame()

    df = df.dropna(subset=["stock_id", "close", "open", "Trading_Volume"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["stock_id", "date"])

    latest_trading_date = df["date"].max()

    results = []
    for stock_id, g in df.groupby("stock_id"):
        try:
            g = g.sort_values("date")
            if len(g) < 20:
                continue  # 資料不足 20 個交易日，無法算 20MA，安全跳過

            g["ma5"] = g["close"].rolling(window=5).mean()
            g["ma20"] = g["close"].rolling(window=20).mean()
            g["vol_ma20"] = g["Trading_Volume"].rolling(window=20).mean()

            today_row = g[g["date"] == latest_trading_date]
            if today_row.empty:
                continue  # 該股當天沒有成交資料（例如停牌），安全跳過
            today_row = today_row.iloc[-1]

            if pd.isna(today_row["ma5"]) or pd.isna(today_row["ma20"]) or pd.isna(today_row["vol_ma20"]):
                continue
            if today_row["vol_ma20"] <= 0:
                continue

            close = float(today_row["close"])
            volume_multiplier = float(today_row["Trading_Volume"]) / float(today_row["vol_ma20"])

            if (
                close > today_row["ma5"]
                and close > today_row["ma20"]
                and volume_multiplier > VOLUME_MULTIPLIER_THRESHOLD
            ):
                results.append(
                    {
                        "stock_id": stock_id,
                        "stock_name": today_row["stock_name"],
                        "current_price": close,
                        "stop_loss_price": float(today_row["open"]),
                        "volume_multiplier": round(volume_multiplier, 2),
                    }
                )
        except Exception as e:
            # 單一股票計算失敗不能讓整個掃描當機，記錄後跳過即可
            logger.warning(f"[技術面] 股票 {stock_id} 計算失敗，已跳過：{e}")
            continue

    return latest_trading_date.strftime("%Y-%m-%d"), pd.DataFrame(results)


# ======================================================================
# 5. 籌碼面：投信連續買超天數（全市場 = 上市 TWSE + 上櫃 TPEx）
# ======================================================================
def _fetch_institutional_all_markets(lookback_calendar_days: int = 15) -> pd.DataFrame:
    """平行抓上市 + 上櫃的投信買賣超歷史並合併，理由同 _fetch_market_ohlc_all_markets()。"""
    with ThreadPoolExecutor(max_workers=2) as executor:
        twse_future = executor.submit(twse_data.fetch_institutional_history, lookback_calendar_days)
        tpex_future = executor.submit(tpex_data.fetch_institutional_history, lookback_calendar_days)
        twse_df = twse_future.result()
        tpex_df = tpex_future.result()
    return pd.concat([twse_df, tpex_df], ignore_index=True)


def analyze_institutional_market(min_consecutive_days: int = INSTITUTIONAL_STREAK_DAYS) -> pd.DataFrame:
    """
    籌碼面計算，範圍是全市場（上市 TWSE 的 T86 端點 + 上櫃 TPEx 對應端點）。

    - _fetch_institutional_all_markets() 平行抓兩邊最近 15 個日曆天的投信
      買賣超並合併（兩邊都已經只留「投信」淨買超，不用再過濾類別欄位）。
    - 篩選出「從最新交易日往前算，連續買超 > 0」天數 >= min_consecutive_days 的股票。

    回傳欄位：stock_id / institutional_buy_days
    """
    df = _fetch_institutional_all_markets(lookback_calendar_days=15)
    if df.empty:
        logger.warning("[籌碼面] 全市場三大法人資料為空")
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"])

    results = []
    for stock_id, g in df.groupby("stock_id"):
        try:
            g = g.sort_values("date", ascending=False)  # 由最新交易日往前排
            streak = 0
            for _, row in g.iterrows():
                if row["net_buy"] > 0:
                    streak += 1
                else:
                    break
            if streak >= min_consecutive_days:
                results.append({"stock_id": stock_id, "institutional_buy_days": int(streak)})
        except Exception as e:
            logger.warning(f"[籌碼面] 股票 {stock_id} 計算失敗，已跳過：{e}")
            continue

    return pd.DataFrame(results)


# ======================================================================
# 6. 基本面：營收年增率 + 股本篩選（全市場 = 上市 TWSE + 上櫃 TPEx）
# ======================================================================
def analyze_revenue_and_capital_market() -> pd.DataFrame:
    """
    基本面計算，範圍是全市場（上市 TWSE + 上櫃 TPEx）。

    - fetch_revenue_yoy_all()：全市場最新月營收年增率——TWSE / TPEx 這兩支
      資料集自己就已經算好年增率，不用像 FinMind 版那樣自己抓歷史再手動算。
    - fetch_capital_all()：全市場「實收資本額」，是真正的股本數字，不是像
      先前 FinMind 版那樣用市值反推的估計值。
    - 篩選：營收年增率 > REVENUE_YOY_THRESHOLD 且 股本 < CAPITAL_LIMIT。
    - 上市、上櫃四支資料（各兩邊各一支）用 ThreadPoolExecutor 一次平行抓完。

    回傳欄位：stock_id / revenue_growth_yoy
    """
    with ThreadPoolExecutor(max_workers=4) as executor:
        twse_rev_future = executor.submit(twse_data.fetch_revenue_yoy_all)
        tpex_rev_future = executor.submit(tpex_data.fetch_revenue_yoy_all)
        twse_cap_future = executor.submit(twse_data.fetch_capital_all)
        tpex_cap_future = executor.submit(tpex_data.fetch_capital_all)
        rev_df = pd.concat([twse_rev_future.result(), tpex_rev_future.result()], ignore_index=True)
        cap_df = pd.concat([twse_cap_future.result(), tpex_cap_future.result()], ignore_index=True)

    if rev_df.empty:
        logger.warning("[基本面] 全市場月營收資料為空")
        return pd.DataFrame()

    rev_df = rev_df[rev_df["revenue_growth_yoy"] > REVENUE_YOY_THRESHOLD]
    if rev_df.empty:
        return pd.DataFrame()

    if cap_df.empty:
        logger.warning("[基本面] 股本資料為空，本次掃描跳過股本篩選（僅以營收年增率為準）")
        return rev_df[["stock_id", "revenue_growth_yoy"]]

    merged = rev_df.merge(cap_df, on="stock_id", how="inner")
    merged = merged[merged["capital"] < CAPITAL_LIMIT]
    return merged[["stock_id", "revenue_growth_yoy"]]


# ======================================================================
# 7. 三大生態合併（全市場 = 上市 TWSE + 上櫃 TPEx，約 1800 多檔）
# ======================================================================
def run_full_scan() -> tuple:
    """
    掃描主流程：技術面 -> 籌碼面 -> 基本面，三者在本地端取交集（inner join），
    只有同時符合三大條件的股票才會出現在最終結果。三個條件都是「上市 + 上櫃」
    全市場範圍，股票名稱已經在技術面那一步從行情資料裡帶出來了，不用再另外查一次。

    回傳 (trading_date, results)：trading_date 是這次掃描實際採用的「最新結算
    交易日」（TWSE/TPEx 收盤後才會公布的資料，不是當下即時盤中報價），前端要
    用這個日期跟使用者說清楚「資料截至哪一天」，避免被誤會成即時行情。
    """
    logger.info("=== 開始三大生態選股掃描（全市場：上市 TWSE + 上櫃 TPEx）===")

    trading_date, tech_df = analyze_technical_market()
    if trading_date is None:
        raise RuntimeError("無法取得最新交易日的股價資料，請確認證交所/櫃買中心服務是否正常，或稍後再試")
    logger.info(f"[技術面] 最新交易日：{trading_date}，通過篩選：{len(tech_df)} 檔")

    if tech_df.empty:
        return trading_date, []

    inst_df = analyze_institutional_market()
    logger.info(f"[籌碼面] 通過篩選：{len(inst_df)} 檔")
    if inst_df.empty:
        return trading_date, []

    fundamental_df = analyze_revenue_and_capital_market()
    logger.info(f"[基本面] 通過篩選：{len(fundamental_df)} 檔")
    if fundamental_df.empty:
        return trading_date, []

    # ---- 三大條件取交集 ----
    merged = tech_df.merge(inst_df, on="stock_id", how="inner")
    merged = merged.merge(fundamental_df, on="stock_id", how="inner")

    if merged.empty:
        return trading_date, []

    # ---- 對齊前端表格欄位順序 ----
    output_columns = [
        "stock_id",
        "stock_name",
        "current_price",
        "volume_multiplier",
        "revenue_growth_yoy",
        "institutional_buy_days",
        "stop_loss_price",
    ]
    for col in output_columns:
        if col not in merged.columns:
            merged[col] = None

    merged = merged[output_columns].sort_values("volume_multiplier", ascending=False)

    logger.info(f"=== 掃描完成，最終符合三大生態條件：{len(merged)} 檔 ===")
    return trading_date, _json_safe(merged.to_dict(orient="records"))


# ======================================================================
# 7.5 掃描結果本地快取：同一天內重複請求不用重新掃描
# ======================================================================
def _load_scan_cache() -> Optional[dict]:
    """
    讀取本地掃描快取。只有當快取檔案存在、而且是「今天」存的，才會被採用；
    跨天的舊快取視為過期（回傳 None），讓呼叫端重新掃描。檔案不存在、損毀、
    或格式不對，都只當作沒有快取處理，不會讓 API 掛掉。
    """
    if not SCAN_CACHE_FILE.exists():
        return None
    try:
        with open(SCAN_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if cache.get("scan_date") != date.today().isoformat():
            logger.info("[快取] 快取是之前某一天存的，視為過期")
            return None
        return cache
    except Exception as e:
        logger.warning(f"[快取] 讀取掃描快取失敗，視為沒有快取：{e}")
        return None


def _save_scan_cache(scan_time: str, trading_date: str, results: list) -> None:
    """
    把掃描結果寫進本地快取檔案。用「先寫暫存檔、再原子性 rename」的方式，
    避免另一個請求剛好在讀取時，讀到寫到一半的檔案。寫入失敗只記錄 log，
    不影響這次已經算好、準備回傳給前端的結果。
    """
    cache = {
        "scan_date": date.today().isoformat(),
        "scan_time": scan_time,
        "trading_date": trading_date,
        "total_count": len(results),
        "data": results,
    }
    tmp_path = SCAN_CACHE_FILE.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        tmp_path.replace(SCAN_CACHE_FILE)  # 原子性覆蓋，不會有寫一半的中間狀態
    except Exception as e:
        logger.warning(f"[快取] 寫入掃描快取失敗，不影響本次回傳結果：{e}")


# ======================================================================
# 7.6 排程：收盤後自動掃描一次，讓快取在使用者打開網站前就是熱的
# ======================================================================
# 為什麼是收盤後、不是開盤時？實測過：台灣時間早上開盤前直接問證交所「今天」
# 的收盤行情表，回傳「沒有符合條件的資料」——這幾支免費端點是收盤後才會產生
# 當天的完整報表，不是逐筆即時更新，開盤當下掃跟收盤前掃拿到的都還是前一個
# 交易日的舊資料，早跑沒有意義。時間選在收盤（13:30）後一小時（14:30），
# 給證交所/櫃買中心足夠時間把報表整理發布完成。
#
# 14:30 台灣時間（UTC+8）換算成 UTC 是當天 06:30，跟台灣當天日期同一天，
# 所以就算 Railway 容器用 UTC 系統時間，_save_scan_cache() 裡的
# date.today() 算出來的 scan_date 也不會跨日出錯；但這個排程時間如果之後
# 改到台灣時間凌晨 0-8 點，UTC 那邊會是前一天，屆時要另外處理時區換算，
# 不能直接假設 date.today() 就是台灣的今天。
def _scheduled_scan_job() -> None:
    """收盤後自動掃描一次；跟 API 路由共用同一把鎖，若當下有人正在手動掃描/回測就跳過，不搶鎖。"""
    acquired = heavy_task_lock.acquire(blocking=False)
    if not acquired:
        logger.info("[排程] 收盤後自動掃描時間到，但目前有掃描/回測正在執行，本次跳過")
        return
    try:
        logger.info("[排程] 開始收盤後自動掃描")
        trading_date, results = run_full_scan()
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_scan_cache(scan_time, trading_date, results)
        logger.info(f"[排程] 收盤後自動掃描完成，交易日 {trading_date}，符合條件 {len(results)} 檔")
    except Exception as e:
        logger.exception(f"[排程] 收盤後自動掃描失敗：{e}")
    finally:
        heavy_task_lock.release()


# ======================================================================
# 7.7 排程：收盤後自動記錄一次 Codex 的鎖定參數紙上交易訊號
# ======================================================================
# 這是 Codex 的研究工具（見 STRATEGY_RESEARCH_REPORT.md 第9節、
# locked_strategy_paper_trade.py），不是正式站選股邏輯的一部分——只是把
# 「用 point-in-time 驗證過的候選參數（量能1.5x + 2ATR停損等）今天會選到
# 哪些股票」記錄到本地的 paper_trade_ledger.jsonl，之後追蹤這些訊號實際
# 表現，驗證候選策略在完全沒看過的新資料上是否真的站得住腳。
#
# 原本要靠 Codex 自己記得手動執行，容易漏掉某幾天，導致紙上交易樣本有
# 缺口；改成排程自動跑，確保報告要求的「累積 3-6 個月新訊號」不會因為
# 忘記手動執行而中斷。
#
# 排在收盤掃描（14:30）之後 15 分鐘（14:45）執行，用 from_cache=True
# 直接讀當天已經掃好的正式快取，不用再對 TWSE/TPEx 重新發一次全市場請求
# ——省時間，也不會讓兩個排程同時打對方伺服器提高被限流的風險。
#
# main.py 內部才 import locked_strategy_paper_trade，是刻意延後：那支腳本
# 自己也會 `import main`，如果在這裡的模組最上方就 import，main.py 都還
# 沒載入完成就會造成循環匯入錯誤，延後到函式實際執行時才 import 就沒事
# （那時候 main 這個模組早就在 sys.modules 裡載入完成了）。
def _scheduled_paper_trade_job() -> None:
    """收盤後自動記錄一次 Codex 鎖定參數的紙上交易訊號；只寫本地 ledger，不影響正式站任何邏輯。"""
    try:
        import locked_strategy_paper_trade

        logger.info("[紙上交易] 開始記錄鎖定參數訊號")
        result = locked_strategy_paper_trade.run(from_cache=True)
        logger.info(f"[紙上交易] 記錄完成，新增 {result['new_records_appended']} 筆訊號")
    except Exception as e:
        logger.exception(f"[紙上交易] 記錄失敗：{e}")


_scan_scheduler = BackgroundScheduler(timezone="Asia/Taipei")
_scan_scheduler.add_job(
    _scheduled_scan_job,
    trigger=CronTrigger(day_of_week="mon-fri", hour=14, minute=30, timezone="Asia/Taipei"),
    id="post_market_scan",
    replace_existing=True,
)
_scan_scheduler.add_job(
    _scheduled_paper_trade_job,
    trigger=CronTrigger(day_of_week="mon-fri", hour=14, minute=45, timezone="Asia/Taipei"),
    id="post_market_paper_trade",
    replace_existing=True,
)
_scan_scheduler.start()


@app.on_event("shutdown")
def _shutdown_scheduler() -> None:
    _scan_scheduler.shutdown(wait=False)


# ======================================================================
# 8. 回測模組：驗證「三大生態選股」規則過去的勝率，而不是只看今天符不符合
# ======================================================================
"""
為什麼需要這一段？
單純的「今天符不符合條件」的篩選器，沒辦法告訴你這套規則到底準不準——
也就是完全不知道「勝率」。這裡做的事情是：把過去 BACKTEST_LOOKBACK_DAYS
天內，WATCHLIST 每一檔股票「逐日」用跟 run_full_scan() 完全相同的四個條件
（技術面 + 籌碼面 + 基本面 + 股本）去檢查，找出所有「訊號日」，然後模擬
「訊號隔天開盤買進、之後持有 N 個交易日再賣出」，統計這些訊號的勝率、
平均報酬、最好/最差報酬。

【老實講在前面的限制，不要被數字誤導】
1. 樣本數受限於 WATCHLIST 大小（目前 100 檔，股本 < 40 億的中小型股，依流動性
   排名取前 100，見 WATCHLIST 定義處說明）與回測窗口。訊號數量（signal_count）
   比勝率本身更該優先看，看到小樣本的漂亮數字不要直接當結論；用這 100 檔測
   五年的訊號數通常有數百到數千筆，比舊的大型股清單健康很多，但仍是「今天
   選出的清單」回頭測過去，不是「回測起點當天真實存在的中小型股全集」，
   有一定的存活者偏誤（詳見 build_small_cap_watchlist.py 的選股方法）。
2. 進場價是「訊號隔天開盤價」，已經算進手續費（BACKTEST_FEE_RATE）、
   賣出證交稅（BACKTEST_SELL_TAX_RATE）、單邊滑價（BACKTEST_SLIPPAGE_RATE），
   不是零成本的樂觀版本，但實際成交價還是可能因為市場衝擊而更差。
3. 沒有處理下市、減資、除權息造成的價格跳動，回測窗口越長，這類雜訊
   可能越明顯。
4. 營收、股本兩個條件都用「財報/資料實際公佈日」（而非資料代表的期別）
   當生效日，避免用到「當時根本還沒公佈」的未來資訊（look-ahead bias）：
   營收用 create_time；股本用資產負債表的期末日 + 60~90 天概估公佈延遲
   （Q1-Q3 加 60 天、年報加 90 天），沒有精確到每家公司實際公告日。
5. 同一檔股票連續多天都符合條件，只算第一天是一次訊號，避免同一波
   行情被拆成好幾筆「獨立」交易，虛增樣本數跟高估勝率。
這是方法論上算合理的版本，但還不到能拿來真的下注的嚴謹程度，比較適合
拿來判斷「這套規則的方向對不對」，而不是精確的勝率數字。
"""
BACKTEST_LOOKBACK_DAYS = 1825  # 預設五年，至少覆蓋不同多空階段，避免只看近一年
BACKTEST_HOLDING_PERIODS = [5, 10, 20]  # 訊號出現後，分別模擬持有幾個「交易日」再賣出
# 保守估計單邊滑價 0.10%；手續費以未打折 0.1425% 計，賣出再加股票交易稅 0.30%。
# 成本直接反映在每筆報酬，不再顯示容易誤導的「零成本勝率」。
BACKTEST_FEE_RATE = 0.001425
BACKTEST_SELL_TAX_RATE = 0.003
BACKTEST_SLIPPAGE_RATE = 0.001


def _compute_backtest_signals_for_stock(
    stock_id: str,
    price_df: pd.DataFrame,
    inst_df: pd.DataFrame,
    rev_df: pd.DataFrame,
    balance_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    針對單一股票，把技術面/籌碼面/基本面/股本四個條件在整段歷史上逐日算成布林值、
    取交集，找出所有「訊號日」，並計算之後 N 個交易日的報酬率。

    balance_df 是選填的（傳 None 或空表時，股本條件視為一律通過）——因為
    這個函式也被 /api/backtest 以外的地方直接呼叫過（研究腳本），保留舊呼叫
    方式不會壞掉，同時讓 /api/backtest 真的套用「股本 < CAPITAL_LIMIT」，
    才會跟 /api/scan（即時掃描）測的是同一套四條件策略，而不是少一個條件。

    回傳欄位：stock_id / signal_date / entry_price / return_5 / return_10 / return_20
    （return_N 為 None 表示訊號日離今天太近，還沒走完那個持有期，不是計算錯誤）
    """
    if price_df.empty or len(price_df) < 25:
        return pd.DataFrame()

    price_df = price_df.dropna(subset=["stock_id", "close", "Trading_Volume"]).copy()
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.sort_values("date").reset_index(drop=True)

    # ---- 技術面訊號（向量化逐日計算，判斷邏輯跟 analyze_technical_market() 相同）----
    price_df["ma5"] = price_df["close"].rolling(5).mean()
    price_df["ma20"] = price_df["close"].rolling(20).mean()
    price_df["vol_ma20"] = price_df["Trading_Volume"].rolling(20).mean()
    price_df["tech_signal"] = (
        (price_df["close"] > price_df["ma5"])
        & (price_df["close"] > price_df["ma20"])
        & (price_df["vol_ma20"] > 0)
        & (price_df["Trading_Volume"] > price_df["vol_ma20"] * VOLUME_MULTIPLIER_THRESHOLD)
    )

    # ---- 籌碼面訊號（投信連續買超 >= INSTITUTIONAL_STREAK_DAYS 天，判斷邏輯跟 analyze_institutional_market() 相同）----
    if inst_df.empty:
        price_df["inst_signal"] = False
    else:
        inst_df = inst_df.dropna(subset=["date", "buy", "sell"]).copy()
        inst_df["date"] = pd.to_datetime(inst_df["date"])
        inst_df["net_buy"] = inst_df["buy"] - inst_df["sell"]
        inst_df = inst_df.sort_values("date")
        streak_ok = inst_df["net_buy"] > 0
        for lag in range(1, INSTITUTIONAL_STREAK_DAYS):
            streak_ok = streak_ok & (inst_df["net_buy"].shift(lag) > 0).fillna(False)
        inst_df["inst_signal"] = streak_ok
        price_df = price_df.merge(inst_df[["date", "inst_signal"]], on="date", how="left")
        price_df["inst_signal"] = price_df["inst_signal"].fillna(False)

    # ---- 基本面訊號（營收年增率，用 create_time 當生效日避免用到未來資料）----
    if rev_df.empty:
        price_df["revenue_signal"] = False
    else:
        rev_df = rev_df.dropna(subset=["revenue", "revenue_month", "revenue_year"]).copy()
        rev_df["effective_date"] = pd.to_datetime(
            rev_df["create_time"].replace("", pd.NA), errors="coerce"
        ).astype("datetime64[ns]")
        rev_df["effective_date"] = rev_df["effective_date"].fillna(
            pd.to_datetime(rev_df["date"], errors="coerce").astype("datetime64[ns]")
        )
        rev_df = rev_df.sort_values(["revenue_year", "revenue_month"]).reset_index(drop=True)

        yoy_records = []
        for idx in range(len(rev_df)):
            row = rev_df.iloc[idx]
            mask = (rev_df["revenue_year"] == row["revenue_year"] - 1) & (
                rev_df["revenue_month"] == row["revenue_month"]
            )
            prev = rev_df[mask]
            if prev.empty or not prev.iloc[-1]["revenue"] or pd.isna(row["effective_date"]):
                continue
            last_year_revenue = prev.iloc[-1]["revenue"]
            yoy = (row["revenue"] - last_year_revenue) / last_year_revenue * 100
            yoy_records.append({"effective_date": row["effective_date"], "yoy_pass": yoy > REVENUE_YOY_THRESHOLD})

        if not yoy_records:
            price_df["revenue_signal"] = False
        else:
            yoy_df = pd.DataFrame(yoy_records).sort_values("effective_date")
            yoy_df["effective_date"] = pd.to_datetime(yoy_df["effective_date"]).astype("datetime64[ns]")
            price_df["date"] = pd.to_datetime(price_df["date"]).astype("datetime64[ns]")
            price_df = pd.merge_asof(
                price_df.sort_values("date"),
                yoy_df,
                left_on="date",
                right_on="effective_date",
                direction="backward",
            )
            price_df["revenue_signal"] = price_df["yoy_pass"].fillna(False)

    # ---- 股本訊號（股本 < CAPITAL_LIMIT，用財報公佈延遲當生效日避免用到未來資料）----
    # FinMind 資產負債表的 date 是財報「期末日」，不是「公告日」，實際公佈本來就會
    # 延遲：Q1-Q3 財報依規定 45 天內公告（這裡保守抓 60 天），年報 90 天內公告。
    # 一般產業用 CapitalStock（股本合計）；金融業報表只提供 OrdinaryShare，兩者
    # 同期都有時以 CapitalStock 優先，邏輯跟 backtest_relaxation_analysis.py 一致。
    if balance_df is None or balance_df.empty:
        price_df["capital_signal"] = True  # 沒有股本資料時視為一律通過，不因為缺資料就整批排除
    else:
        capital = balance_df[balance_df["type"].isin(["CapitalStock", "OrdinaryShare"])][
            ["date", "type", "value"]
        ].copy()
        if capital.empty:
            price_df["capital_signal"] = True
        else:
            capital["type_priority"] = capital["type"].map({"OrdinaryShare": 0, "CapitalStock": 1})
            capital = capital.sort_values(["date", "type_priority"]).drop_duplicates("date", keep="last")
            capital["report_date"] = pd.to_datetime(capital["date"])
            capital["effective_date"] = capital["report_date"] + capital["report_date"].dt.month.map(
                lambda month: pd.Timedelta(days=90 if month == 12 else 60)
            )
            capital["effective_date"] = capital["effective_date"].astype("datetime64[ns]")
            capital = capital.sort_values("effective_date").drop_duplicates("effective_date", keep="last")
            price_df["date"] = pd.to_datetime(price_df["date"]).astype("datetime64[ns]")
            price_df = pd.merge_asof(
                price_df.sort_values("date"),
                capital[["effective_date", "value"]].rename(columns={"value": "capital_value"}),
                left_on="date",
                right_on="effective_date",
                direction="backward",
            )
            price_df["capital_signal"] = (price_df["capital_value"] < CAPITAL_LIMIT).fillna(False)

    raw_signal = (
        price_df["tech_signal"]
        & price_df["inst_signal"]
        & price_df["revenue_signal"]
        & price_df["capital_signal"]
    )
    # 連續數日都符合只視為同一次訊號，避免同一波行情被重複計權。
    price_df["signal"] = raw_signal & ~raw_signal.shift(1, fill_value=False)

    signal_rows = price_df[price_df["signal"]]
    if signal_rows.empty:
        return pd.DataFrame()

    records = []
    for idx in signal_rows.index:
        entry_idx = idx + 1
        if entry_idx >= len(price_df) or pd.isna(price_df.loc[entry_idx, "open"]):
            continue
        # 日線收盤後才能確認量價與法人條件，因此最早只能在次日開盤成交。
        raw_entry_price = float(price_df.loc[entry_idx, "open"])
        if raw_entry_price <= 0:
            continue  # 開盤價異常（停牌/資料缺漏），跳過避免後面除以零產生 inf/nan
        entry_price = raw_entry_price * (1 + BACKTEST_SLIPPAGE_RATE)
        record = {
            "stock_id": stock_id,
            "signal_date": price_df.loc[idx, "date"].strftime("%Y-%m-%d"),
            "entry_date": price_df.loc[entry_idx, "date"].strftime("%Y-%m-%d"),
            "entry_price": round(entry_price, 2),
        }
        for holding in BACKTEST_HOLDING_PERIODS:
            exit_idx = entry_idx + holding
            if exit_idx < len(price_df):
                exit_price = float(price_df.loc[exit_idx, "close"]) * (1 - BACKTEST_SLIPPAGE_RATE)
                gross_multiple = exit_price / entry_price
                net_multiple = (
                    gross_multiple
                    * (1 - BACKTEST_FEE_RATE)
                    * (1 - BACKTEST_SELL_TAX_RATE)
                    / (1 + BACKTEST_FEE_RATE)
                )
                record[f"return_{holding}"] = round((net_multiple - 1) * 100, 2)
            else:
                record[f"return_{holding}"] = None  # 訊號日太接近今天，還沒走完這個持有期
        records.append(record)

    return pd.DataFrame(records)


def run_backtest() -> dict:
    """
    回測主流程：對 WATCHLIST 每一檔股票，抓歷史資料 -> 逐日計算四條件訊號
    -> 依持有天數分別統計勝率與報酬。方法論上的限制見本節開頭的說明文字。

    四條件 = 技術面 + 籌碼面 + 基本面 + 股本（跟 /api/scan 即時掃描同一套規則，
    2026-07 之前的版本少了股本這個條件，回測結果沒辦法直接拿來對照即時掃描的
    表現，這裡補上之後兩邊測的才是同一套策略）。
    """
    logger.info(f"=== 開始回測（觀察清單 {len(WATCHLIST)} 檔，回溯 {BACKTEST_LOOKBACK_DAYS} 天）===")

    end_date = date.today()
    # 營收/股本都要多抓將近一年的緩衝，才能算出回測窗口「最早那一天」的年增率／股本
    price_start = (end_date - timedelta(days=BACKTEST_LOOKBACK_DAYS + 40)).isoformat()
    inst_start = (end_date - timedelta(days=BACKTEST_LOOKBACK_DAYS + 10)).isoformat()
    rev_start = (end_date - timedelta(days=BACKTEST_LOOKBACK_DAYS + 400)).isoformat()
    end_iso = end_date.isoformat()

    all_signals = []
    for stock_id in WATCHLIST:
        try:
            price_df = _finmind_get("TaiwanStockPrice", price_start, end_iso, data_id=stock_id)
            inst_df = _finmind_get(
                "TaiwanStockInstitutionalInvestorsBuySell", inst_start, end_iso, data_id=stock_id
            )
            if not inst_df.empty and "name" in inst_df.columns:
                inst_df = inst_df[inst_df["name"] == INVESTMENT_TRUST_NAME]
            rev_df = _finmind_get("TaiwanStockMonthRevenue", rev_start, end_iso, data_id=stock_id)
            balance_df = _finmind_get("TaiwanStockBalanceSheet", rev_start, end_iso, data_id=stock_id)

            signals = _compute_backtest_signals_for_stock(stock_id, price_df, inst_df, rev_df, balance_df)
            if not signals.empty:
                all_signals.append(signals)
        except Exception as e:
            # 單一股票回測失敗不能讓整個回測當機，記錄後跳過即可
            logger.warning(f"[回測] 股票 {stock_id} 計算失敗，已跳過：{e}")
            continue

    if not all_signals:
        logger.info("=== 回測完成，回測窗口內沒有出現任何訊號 ===")
        return {"summary": {}, "signals": []}

    signals_df = pd.concat(all_signals, ignore_index=True)

    # 抓資料時多抓了緩衝天數，這裡篩掉早於回測窗口起點的訊號
    cutoff = pd.Timestamp(end_date - timedelta(days=BACKTEST_LOOKBACK_DAYS))
    signals_df["signal_date_dt"] = pd.to_datetime(signals_df["signal_date"])
    signals_df = signals_df[signals_df["signal_date_dt"] >= cutoff].drop(columns=["signal_date_dt"])

    if signals_df.empty:
        return {"summary": {}, "signals": []}

    # ---- 補上股票名稱 ----
    info_df = _finmind_get("TaiwanStockInfo", "2000-01-01")
    if not info_df.empty and "stock_name" in info_df.columns:
        info_df = info_df.drop_duplicates(subset=["stock_id"], keep="last")
        signals_df = signals_df.merge(info_df[["stock_id", "stock_name"]], on="stock_id", how="left")
    else:
        signals_df["stock_name"] = None
    signals_df["stock_name"] = signals_df["stock_name"].fillna(signals_df["stock_id"])

    # ---- 依持有天數分別統計勝率／報酬 ----
    summary = {}
    for holding in BACKTEST_HOLDING_PERIODS:
        col = f"return_{holding}"
        valid = signals_df[col].dropna()
        if valid.empty:
            summary[str(holding)] = None
            continue
        wins = valid[valid > 0]
        losses = valid[valid <= 0]
        summary[str(holding)] = {
            "signal_count": int(len(valid)),
            "win_rate": round(len(wins) / len(valid) * 100, 1),
            "avg_return": round(float(valid.mean()), 2),
            "avg_win": round(float(wins.mean()), 2) if not wins.empty else None,
            "avg_loss": round(float(losses.mean()), 2) if not losses.empty else None,
            "best": round(float(valid.max()), 2),
            "worst": round(float(valid.min()), 2),
            "median_return": round(float(valid.median()), 2),
            "profit_factor": round(float(wins.sum() / abs(losses.sum())), 2)
            if not losses.empty and losses.sum() != 0
            else None,
        }

    signals_df = signals_df.sort_values("signal_date", ascending=False)
    signal_list = signals_df.head(100).to_dict(orient="records")

    logger.info(f"=== 回測完成，回測窗口內共 {len(signals_df)} 次訊號 ===")
    return _json_safe({"summary": summary, "signals": signal_list})


# ======================================================================
# 9. 個股詳情（股票比較／個股詳情頁用，資料來源 FinMind，單股查詢）
# ======================================================================
"""
為什麼這裡改用 FinMind，不是 TWSE/TPEx？
/api/scan、/api/backtest 都是「掃全市場」，一次呼叫拿全部股票的資料比較
划算，所以值得花力氣清洗 TWSE/TPEx 的原始格式。但這支端點是「查一檔
股票」，情境完全相反：FinMind 的 data_id 單股查詢幾次請求就好，改用
TWSE/TPEx 反而要把全市場資料抓下來才能挑出一檔，划不來。所以個股查詢
繼續用 FinMind，股本／市值則是唯一例外——TWSE/TPEx 的股本資料集本來就是
「一次拿全部」的批次端點，沒有更精準的單股股本查詢，所以還是呼叫那兩支，
只是查完只取需要的那一檔。
"""


def _compute_technical_indicators(close: pd.Series) -> dict:
    """
    用收盤價序列算 RSI(14)、MACD(12,26,9)、MA20/50/200，只回傳「最新一天」
    的數值。資料不夠算某項指標時，該欄位回傳 None，不會拋例外。
    """

    def _last_or_none(series: pd.Series) -> Optional[float]:
        if series.empty:
            return None
        value = series.iloc[-1]
        return round(float(value), 2) if pd.notna(value) else None

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    return {
        "rsi": _last_or_none(rsi),
        "macd": _last_or_none(macd_line),
        "signal": _last_or_none(signal_line),
        "histogram": _last_or_none(histogram),
        "ma20": _last_or_none(close.rolling(20).mean()),
        "ma50": _last_or_none(close.rolling(50).mean()),
        "ma200": _last_or_none(close.rolling(200).mean()),
    }


def _fetch_stock_capital_info(stock_id: str) -> dict:
    """
    查單一股票的股本／在外流通股數，先查 TWSE 全市場股本表，查不到再查
    TPEx（一檔股票只會存在其中一邊）。任何一步失敗都回傳全 None，不拋例外。
    """
    try:
        cap_df = twse_data.fetch_capital_all()
        row = cap_df[cap_df["stock_id"] == stock_id]
        if row.empty:
            cap_df = tpex_data.fetch_capital_all()
            row = cap_df[cap_df["stock_id"] == stock_id]
        if not row.empty:
            capital = row.iloc[0].get("capital")
            shares = row.iloc[0].get("shares_outstanding")
            return {
                "capital": float(capital) if pd.notna(capital) else None,
                "shares_outstanding": float(shares) if pd.notna(shares) else None,
            }
    except Exception as e:
        logger.warning(f"[個股詳情] 股票 {stock_id} 查詢股本失敗，已跳過：{e}")

    return {"capital": None, "shares_outstanding": None}


CHART_DISPLAY_DAYS = 120  # 股價走勢圖顯示的交易日數，約半年，足夠看出中期趨勢又不會太擠


def fetch_stock_detail(stock_id: str) -> Optional[dict]:
    """
    查單一股票的完整詳情：價格走勢、技術指標、本益比/淨值比/殖利率、市值、
    營收趨勢（含年增率）、投信近期買賣超明細。查無此股票代號時回傳 None，
    由呼叫端轉成 HTTP 404。除了「查無此股」這個情況，其餘每個子區塊都各自
    try/except 包好，任何一塊失敗只記錄 log、該欄位留空，不會讓整支 API 掛掉。
    """
    end_date = date.today()
    price_start = (end_date - timedelta(days=400)).isoformat()  # 400 天確保湊得到 200 個交易日算 MA200
    price_df = _finmind_get("TaiwanStockPrice", price_start, end_date.isoformat(), data_id=stock_id)
    if price_df.empty:
        return None  # 查無此股票代號

    price_df = price_df.dropna(subset=["close", "open", "Trading_Volume"]).copy()
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.sort_values("date").reset_index(drop=True)
    if price_df.empty:
        return None

    latest = price_df.iloc[-1]
    prev = price_df.iloc[-2] if len(price_df) > 1 else latest
    current_price = float(latest["close"])
    prev_close = float(prev["close"])
    change = current_price - prev_close
    change_percent = (change / prev_close * 100) if prev_close else 0.0
    volume_avg = price_df["Trading_Volume"].rolling(20).mean().iloc[-1]

    # 股價走勢圖要畫真正的技術線圖（K線+均線疊圖），不是只有收盤價的簡單折線，
    # 所以這裡要留下開高低收，並且先在完整的 price_df（最多 400 個日曆天、
    # 約 200 個交易日）上算好 MA5/20/50，再取最後 CHART_DISPLAY_DAYS 筆——
    # 如果先切再算，最前面幾十筆的均線會因為前面沒有資料而是 None，圖表
    # 一開始那段會空一塊。
    price_df["ma5"] = price_df["close"].rolling(5).mean()
    price_df["ma20"] = price_df["close"].rolling(20).mean()
    price_df["ma50"] = price_df["close"].rolling(50).mean()

    price_history = [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["max"]),
            "low": float(row["min"]),
            "close": float(row["close"]),
            "ma5": round(float(row["ma5"]), 2) if pd.notna(row["ma5"]) else None,
            "ma20": round(float(row["ma20"]), 2) if pd.notna(row["ma20"]) else None,
            "ma50": round(float(row["ma50"]), 2) if pd.notna(row["ma50"]) else None,
        }
        for _, row in price_df.tail(CHART_DISPLAY_DAYS).iterrows()
    ]

    technical_indicators = _compute_technical_indicators(price_df["close"])

    # ---- 剩下 5 個子區塊互相獨立，也不需要 price_df 的結果，各自對 FinMind
    # 發一次請求，用執行緒平行查詢——原本是一個接一個序列等，5 個請求疊加的
    # 等待時間很明顯；平行後總時間趨近於「最慢那一個請求」，而不是「全部加總」。
    # 每個子函式仍各自保留原本的 try/except，任何一塊失敗只影響該欄位留空，
    # 不會讓整支 API 掛掉，行為跟平行化之前完全一樣。
    def _fetch_name_industry():
        stock_name, industry = stock_id, None
        try:
            info_df = _finmind_get("TaiwanStockInfo", "2000-01-01", data_id=stock_id)
            if not info_df.empty:
                info_row = info_df.iloc[-1]
                stock_name = info_row.get("stock_name") or stock_id
                industry = info_row.get("industry_category")
        except Exception as e:
            logger.warning(f"[個股詳情] 股票 {stock_id} 查詢名稱失敗，已跳過：{e}")
        return stock_name, industry

    def _fetch_valuation():
        pe = pb = dividend_yield = None
        try:
            per_start = (end_date - timedelta(days=10)).isoformat()
            per_df = _finmind_get("TaiwanStockPER", per_start, end_date.isoformat(), data_id=stock_id)
            if not per_df.empty:
                per_row = per_df.sort_values("date").iloc[-1]
                pe = float(per_row["PER"]) if pd.notna(per_row.get("PER")) else None
                pb = float(per_row["PBR"]) if pd.notna(per_row.get("PBR")) else None
                dividend_yield = (
                    float(per_row["dividend_yield"]) if pd.notna(per_row.get("dividend_yield")) else None
                )
        except Exception as e:
            logger.warning(f"[個股詳情] 股票 {stock_id} 查詢本益比失敗，已跳過：{e}")
        return pe, pb, dividend_yield

    def _fetch_revenue():
        revenue_trend = []
        try:
            rev_start = (end_date - timedelta(days=13 * 31 + 365)).isoformat()  # 多抓一年，才能算最早幾個月的年增率
            rev_df = _finmind_get("TaiwanStockMonthRevenue", rev_start, end_date.isoformat(), data_id=stock_id)
            if not rev_df.empty:
                rev_df = rev_df.dropna(subset=["revenue", "revenue_month", "revenue_year"])
                rev_df = rev_df.sort_values(["revenue_year", "revenue_month"])
                for _, row in rev_df.tail(12).iterrows():
                    mask = (rev_df["revenue_year"] == row["revenue_year"] - 1) & (
                        rev_df["revenue_month"] == row["revenue_month"]
                    )
                    prev_rows = rev_df[mask]
                    yoy = None
                    if not prev_rows.empty and prev_rows.iloc[-1]["revenue"]:
                        yoy = round(
                            (row["revenue"] - prev_rows.iloc[-1]["revenue"]) / prev_rows.iloc[-1]["revenue"] * 100,
                            2,
                        )
                    revenue_trend.append(
                        {
                            "month": f"{int(row['revenue_year'])}-{int(row['revenue_month']):02d}",
                            "revenue": float(row["revenue"]),
                            "yoy": yoy,
                        }
                    )
        except Exception as e:
            logger.warning(f"[個股詳情] 股票 {stock_id} 查詢營收趨勢失敗，已跳過：{e}")
        return revenue_trend

    def _fetch_institutional():
        institutional_recent = []
        try:
            inst_start = (end_date - timedelta(days=20)).isoformat()
            inst_df = _finmind_get(
                "TaiwanStockInstitutionalInvestorsBuySell", inst_start, end_date.isoformat(), data_id=stock_id
            )
            if not inst_df.empty and "name" in inst_df.columns:
                inst_df = inst_df[inst_df["name"] == INVESTMENT_TRUST_NAME].sort_values("date")
                for _, row in inst_df.tail(10).iterrows():
                    buy_lots = float(row["buy"]) / 1000
                    sell_lots = float(row["sell"]) / 1000
                    institutional_recent.append(
                        {
                            "date": row["date"],
                            "buy_lots": round(buy_lots, 1),
                            "sell_lots": round(sell_lots, 1),
                            "net_buy_lots": round(buy_lots - sell_lots, 1),
                        }
                    )
        except Exception as e:
            logger.warning(f"[個股詳情] 股票 {stock_id} 查詢投信買賣超失敗，已跳過：{e}")
        return institutional_recent

    with ThreadPoolExecutor(max_workers=5) as executor:
        name_industry_future = executor.submit(_fetch_name_industry)
        valuation_future = executor.submit(_fetch_valuation)
        capital_future = executor.submit(_fetch_stock_capital_info, stock_id)
        revenue_future = executor.submit(_fetch_revenue)
        institutional_future = executor.submit(_fetch_institutional)

        stock_name, industry = name_industry_future.result()
        pe, pb, dividend_yield = valuation_future.result()
        capital_info = capital_future.result()
        revenue_trend = revenue_future.result()
        institutional_recent = institutional_future.result()

    # ---- 股本／市值（市值 = 真實在外流通股數 × 現價，不是估算值）----
    market_cap = (
        capital_info["shares_outstanding"] * current_price
        if capital_info["shares_outstanding"]
        else None
    )

    return _json_safe({
        "stock_id": stock_id,
        "stock_name": stock_name,
        "industry": industry,
        "current_price": current_price,
        "price_date": latest["date"].strftime("%Y-%m-%d"),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": float(latest["Trading_Volume"]),
        "volume_avg": float(volume_avg) if pd.notna(volume_avg) else None,
        "pe": pe,
        "pb": pb,
        "dividend_yield": dividend_yield,
        "capital": capital_info["capital"],
        "market_cap": market_cap,
        "price_history": price_history,
        "technical_indicators": technical_indicators,
        "revenue_trend": revenue_trend,
        "institutional_recent": institutional_recent,
    })


# ======================================================================
# 9.5 大盤情緒：台指期近月行情 + 三大法人期貨未平倉（首頁小卡片用）
# ======================================================================
# 這是全新的維度（大盤整體氣氛），不是個股選股的第四個條件——三大生態選股
# 的邏輯完全沒變，這裡只是額外提供「今天大盤法人怎麼佈局」的參考資訊。
# 跟現貨資料一樣，這仍然是收盤後才有的資料，不是即時盤中報價（見
# taifex_data.py 開頭說明），一樣要老實揭露資料日期，不能讓人誤會成即時。
MARKET_SENTIMENT_LOOKBACK_DAYS = 10  # 遇到連假時，最多回溯幾個日曆天找最近一個有資料的交易日


def fetch_market_sentiment() -> Optional[dict]:
    """
    找最近一個有資料的交易日，回傳台指期近月行情 + 三大法人期貨未平倉。
    連續 MARKET_SENTIMENT_LOOKBACK_DAYS 天都查不到任何資料（例如連假、TAIFEX
    服務異常）就回傳 None，呼叫端會把整張卡片藏起來，不會顯示殘缺資料。

    期貨行情跟三大法人未平倉是兩份獨立發布的報表，實測發現發布時間不同步——
    早上查詢時，期貨行情（近月合約）可能已經有當天資料（因為台指期有夜盤，
    「今天」的行情其實大部分是前一晚夜盤就交易完成的），但三大法人未平倉
    報表通常要等當天收盤結算後才會產生，同一時間點查詢，兩份報表「最近
    一個有資料的交易日」可能不是同一天。這裡分開回溯，各自找各自最新的，
    不能綁在同一個迴圈裡，不然只要未平倉報表還沒發布，會連已經有的期貨
    行情都一起被擋住不顯示。
    """
    end_date = date.today()

    futures = None
    for offset in range(MARKET_SENTIMENT_LOOKBACK_DAYS):
        futures = taifex_data.fetch_futures_daily(end_date - timedelta(days=offset))
        if futures is not None:
            break
    if futures is None:
        logger.warning(f"[大盤情緒] 回溯 {MARKET_SENTIMENT_LOOKBACK_DAYS} 天都查不到台指期行情，放棄")
        return None

    positions = None
    positions_date = None
    for offset in range(MARKET_SENTIMENT_LOOKBACK_DAYS):
        target_date = end_date - timedelta(days=offset)
        positions = taifex_data.fetch_institutional_futures_positions(target_date)
        if positions is not None:
            positions_date = target_date.isoformat()
            break

    # 拆成三個具名欄位（而不是直接回傳 taifex_data 那個「身份別字串當 key」的 dict），
    # 前端型別才好定義，也不用另外處理混在同一個 dict 裡的 "date" 欄位。
    return {
        "trading_date": futures["date"],
        "futures": futures,
        "positions_date": positions_date,  # 可能跟 trading_date 不同天，見上方說明；前端要各自標示
        "dealer_position": positions.get(taifex_data.DEALER_NAME) if positions else None,
        "trust_position": positions.get(taifex_data.INVESTMENT_TRUST_NAME) if positions else None,
        "foreign_position": positions.get(taifex_data.FOREIGN_INVESTOR_NAME) if positions else None,
    }


# ======================================================================
# 9.6 股票代號／名稱對照表：讓使用者可以用名稱搜尋，不用先知道代號
# ======================================================================
# 首頁的搜尋框只能篩選「今天掃描結果」裡的股票（常常是 0 檔或只有幾檔）、
# 比較頁只能從 8 檔預設權值股按鈕選——整個網站沒有地方能直接打股票代號或
# 名稱跳到個股詳情頁，這裡補上。
#
# 只需要「最近兩個真正有交易的交易日」就能算現價跟漲跌，不用像最初版本
# 那樣不管用不用得到都固定抓 10 個日曆天的完整區間——那個版本在 TPEx
# 不穩定（見 tpex_data.py 開頭已經記錄過好幾次的暫時性 520/連線錯誤/403）
# 時，逐日重試疊加起來會拖很久，正式站實測過一次卡超過 60 秒沒回應。
# 改成逐日回溯、抓到兩個有資料的交易日就停手，正常情況下只要抓 2-3 天，
# 比固定抓 10 天快很多，也不會對 TPEx 發不需要的請求。
#
# 另外加一把鎖：同一時間若有好幾個請求剛好都撞上「快取沒中」，原本會各自
# 獨立觸發一次完整重建，等於同時對 TPEx 開好幾組平行請求，反而更容易被
# 判定成異常流量。有鎖之後，只有第一個請求會真的去抓，其他請求排隊等它
# 做完，直接沿用剛建好的快取，不會疊加負載。
_stock_directory_cache: dict = {"date": None, "data": []}
_stock_directory_lock = threading.Lock()
STOCK_DIRECTORY_LOOKBACK_DAYS = 10  # 遇到連假時，最多回溯幾個日曆天找最近兩個有資料的交易日
STOCK_DIRECTORY_TRADING_DAYS_NEEDED = 2  # 算漲跌只需要「今天」跟「前一天」兩個交易日


def _fetch_stock_directory() -> list:
    frames = []
    end_date = date.today()
    for offset in range(STOCK_DIRECTORY_LOOKBACK_DAYS):
        if len(frames) >= STOCK_DIRECTORY_TRADING_DAYS_NEEDED:
            break
        target_date = end_date - timedelta(days=offset)
        with ThreadPoolExecutor(max_workers=2) as executor:
            twse_future = executor.submit(twse_data.fetch_daily_market_ohlc, target_date)
            tpex_future = executor.submit(tpex_data.fetch_daily_market_ohlc, target_date)
            twse_df = twse_future.result()
            tpex_df = tpex_future.result()
        day_df = pd.concat([twse_df, tpex_df], ignore_index=True)
        if not day_df.empty:
            frames.append(day_df)

    if not frames:
        logger.warning(f"[股票對照表] 回溯 {STOCK_DIRECTORY_LOOKBACK_DAYS} 天都查不到全市場行情，放棄")
        return []

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["stock_id", "stock_name", "close"])
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values(["stock_id", "date"]).drop_duplicates(["stock_id", "date"], keep="last")

    results = []
    for stock_id, group in combined.groupby("stock_id"):
        latest = group.iloc[-1]
        close = float(latest["close"])
        change = change_percent = None
        if len(group) > 1:
            prev_close = float(group.iloc[-2]["close"])
            if prev_close:
                change = round(close - prev_close, 2)
                change_percent = round((close - prev_close) / prev_close * 100, 2)
        results.append(
            {
                "stock_id": stock_id,
                "stock_name": latest["stock_name"],
                "close": close,
                "change": change,
                "change_percent": change_percent,
            }
        )
    return results


def get_stock_directory() -> list:
    """
    當天第一次呼叫才真的重抓，同一天內重複呼叫直接回傳記憶體內快取。用鎖
    確保「快取沒中」時，短時間內湧進來的好幾個請求只有一個會真的觸發重建，
    其他請求排隊等它做完直接沿用結果，不會各自獨立對 TWSE/TPEx 開一輪
    請求、疊加負載（見上方章節開頭的說明）。
    """
    today_str = date.today().isoformat()
    if _stock_directory_cache["date"] == today_str and _stock_directory_cache["data"]:
        return _stock_directory_cache["data"]

    with _stock_directory_lock:
        # 拿到鎖之後再檢查一次快取：如果剛剛是排隊等別人重建，這時候多半
        # 已經有新鮮的快取可以用了，不用自己再重抓一次。
        if _stock_directory_cache["date"] == today_str and _stock_directory_cache["data"]:
            return _stock_directory_cache["data"]
        data = _fetch_stock_directory()
        if data:
            _stock_directory_cache["date"] = today_str
            _stock_directory_cache["data"] = data
        return data


# ======================================================================
# 10. API 路由
# ======================================================================
@app.post("/api/scan")
def scan_stocks(force: bool = False):
    """
    前端「🚀 一鍵掃描全台股」按鈕對應的 API。資料來源是 TWSE 上市 + TPEx
    上櫃（見檔案開頭的架構說明），真的是掃全市場（約 1800 多檔），不受
    WATCHLIST 限制（WATCHLIST 只有 /api/backtest 回測還在用）。

    本地快取：同一個日曆天內，只要成功掃描過一次，結果會存進
    latest_scan_result.json。之後同一天內再打這支 API（例如使用者重新整理
    網頁），直接讀快取秒回，不會重新對 TWSE/TPEx 發出上百次請求。想略過
    快取、強制重新掃描的話，帶查詢參數 ?force=true（換了一天，快取自然
    視為過期，不需要 force 也會重新掃描）。

    防呆機制：用全局鎖（heavy_task_lock，跟 /api/backtest 共用）確保同一時間
    只會有一次運算在跑。若上一次掃描/回測還沒結束，前端重複觸發時直接回傳
    HTTP 423，並附上 JSON 提示文字，避免流量被重複請求打爆。
    """
    if not force:
        cached = _load_scan_cache()
        if cached is not None:
            logger.info(f"[快取] 命中今天的掃描快取（{cached['scan_time']}），直接回傳，不重新掃描")
            return {
                "success": True,
                "scan_time": cached["scan_time"],
                "trading_date": cached.get("trading_date"),
                "total_count": cached["total_count"],
                "data": cached["data"],
                "from_cache": True,
            }

    acquired = heavy_task_lock.acquire(blocking=False)
    if not acquired:
        return JSONResponse(
            status_code=423,
            content={"success": False, "message": "系統全自動計算中，請稍候（上一個掃描/回測尚未完成）"},
        )

    try:
        trading_date, results = run_full_scan()
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_scan_cache(scan_time, trading_date, results)
        return {
            "success": True,
            "scan_time": scan_time,
            "trading_date": trading_date,
            "total_count": len(results),
            "data": results,
            "from_cache": False,
        }
    except Exception as e:
        logger.exception("掃描發生未預期錯誤")
        raise HTTPException(status_code=500, detail=f"掃描過程發生錯誤：{e}")
    finally:
        heavy_task_lock.release()


@app.post("/api/backtest")
def backtest():
    """
    回測 API：驗證「三大生態選股」規則過去 BACKTEST_LOOKBACK_DAYS 天內的勝率，
    不是只看今天符不符合條件（方法論與限制見第 8 節開頭的說明文字）。

    跟 /api/scan 共用同一把鎖（heavy_task_lock）：兩者都要花大量請求跟時間跟
    FinMind 要資料，不應該讓它們同時進行，重複觸發一樣回 423。
    """
    acquired = heavy_task_lock.acquire(blocking=False)
    if not acquired:
        return JSONResponse(
            status_code=423,
            content={"success": False, "message": "系統全自動計算中，請稍候（上一個掃描/回測尚未完成）"},
        )

    try:
        result = run_backtest()
        return {
            "success": True,
            "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "lookback_days": BACKTEST_LOOKBACK_DAYS,
            "holding_periods": BACKTEST_HOLDING_PERIODS,
            "watchlist_size": len(WATCHLIST),
            "summary": result["summary"],
            "signals": result["signals"],
        }
    except Exception as e:
        logger.exception("回測發生未預期錯誤")
        raise HTTPException(status_code=500, detail=f"回測過程發生錯誤：{e}")
    finally:
        heavy_task_lock.release()


@app.get("/api/stock/{stock_id}")
def get_stock_detail(stock_id: str, request: Request):
    """
    股票比較／個股詳情頁用的單股資料 API。跟 /api/scan、/api/backtest 不同，
    這支不用搶 heavy_task_lock——單股查詢只需要幾次 FinMind 請求，幾秒鐘
    就能回應，不是那種需要鎖住、避免重複觸發的重運算。

    每個 IP 每分鐘最多 30 次（見 _enforce_rate_limit）：這支每次呼叫都會
    消耗 FinMind 額度，比較頁一次最多同時查 3 檔，正常使用不太可能撞到。
    """
    _enforce_rate_limit(request, "stock_detail", max_requests=30, window_seconds=60)
    stock_id = stock_id.strip()
    try:
        detail = fetch_stock_detail(stock_id)
    except Exception as e:
        logger.exception(f"查詢股票 {stock_id} 詳細資料發生未預期錯誤")
        raise HTTPException(status_code=500, detail=f"查詢股票資料時發生錯誤：{e}")

    if detail is None:
        raise HTTPException(status_code=404, detail=f"找不到股票代號 {stock_id} 的資料")

    return detail


@app.get("/api/market-sentiment")
def get_market_sentiment(request: Request):
    """
    大盤情緒卡片用的 API：台指期近月行情 + 三大法人期貨未平倉。跟 /api/stock/{id}
    一樣不用搶 heavy_task_lock（只是兩次輕量查詢，幾秒內回應）。

    每個 IP 每分鐘最多 30 次，跟 /api/stock/{id} 用同一個頻率限制邏輯，理由相同。
    """
    _enforce_rate_limit(request, "market_sentiment", max_requests=30, window_seconds=60)
    try:
        sentiment = fetch_market_sentiment()
    except Exception as e:
        logger.exception("查詢大盤情緒發生未預期錯誤")
        raise HTTPException(status_code=500, detail=f"查詢大盤情緒時發生錯誤：{e}")

    if sentiment is None:
        raise HTTPException(status_code=404, detail="目前查不到台指期資料")

    return _json_safe(sentiment)


@app.get("/api/stocks/directory")
def get_stocks_directory():
    """
    全市場股票代號＋名稱對照表，前端拿來做「輸入代號或名稱搜尋、選了就跳到
    個股詳情頁」的全站搜尋框。當天第一次呼叫才會真的對 TWSE/TPEx 發請求
    （見 get_stock_directory() 的記憶體內快取），之後同一天內都是秒回，
    不用加頻率限制。
    """
    directory = get_stock_directory()
    if not directory:
        raise HTTPException(status_code=503, detail="股票清單暫時無法取得，請稍後再試")
    return _json_safe({"stocks": directory})


class ChatRequest(BaseModel):
    user_message: str


@app.post("/api/chat")
def chat(payload: ChatRequest, http_request: Request):
    """
    AI 選股助理。把「今天最新一次 /api/scan 的快取結果」當背景資料塞進
    prompt，讓 AI 根據後端真的算出來的資料回答問題，不是憑空亂講。

    語氣設定成適合長輩／投資新手閱讀（見 chat_assistant.py 的 SYSTEM_PROMPT）。
    這支不用搶 heavy_task_lock——只是讀已經存在的快取檔案 + 呼叫一次 LLM
    API，不是那種要花很久的全市場重運算。

    三層架構（見 chat_assistant.py 開頭說明）：設定 OPENAI_API_KEY 就用
    OpenAI；沒設定就試 GEMINI_API_KEY；兩個都沒設定，退回本地規則式回覆，
    這樣就算還沒申請 LLM 金鑰，聊天功能也不會整個打不開。

    每個 IP 每分鐘最多 10 次（見 _enforce_rate_limit）：這支每次呼叫都會
    消耗 OpenAI/Gemini 額度（真金白銀），是這幾個端點裡最該優先擋濫用的。
    """
    _enforce_rate_limit(http_request, "chat", max_requests=10, window_seconds=60)
    scan_context = _load_scan_cache()
    try:
        result = chat_assistant.generate_reply(payload.user_message, scan_context=scan_context)
        return {"success": True, "reply": result["reply"], "source": result["source"]}
    except Exception as e:
        logger.exception("AI 助理回覆發生未預期錯誤")
        raise HTTPException(status_code=500, detail=f"AI 助理暫時無法回應：{e}")


@app.get("/")
def health_check():
    """簡單的健康檢查路由，確認後端有正常啟動。"""
    return {
        "status": "ok",
        "message": "台股量化選股 API 運作中",
        "scan_data_source": "TWSE 上市 + TPEx 上櫃（全市場）",
        "backtest_watchlist_size": len(WATCHLIST),
        "chat_ai_source": (
            "openai" if os.getenv("OPENAI_API_KEY") else "gemini" if os.getenv("GEMINI_API_KEY") else "fallback（規則式，未設定 AI 金鑰）"
        ),
    }


# ======================================================================
# 11. 本地啟動入口
# ======================================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
