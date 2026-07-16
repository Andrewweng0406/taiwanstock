"""
taifex_data.py — 台灣期貨交易所（TAIFEX）公開資料撈取與清洗
=====================================================================
補上「大盤情緒」這個新維度：台指期近月合約的行情，跟三大法人在期貨的
多空未平倉部位（俗稱「外資期貨未平倉」，市場常拿來當大盤方向的參考指標）。

這是全新的資料來源，跟 twse_data.py / tpex_data.py 完全獨立，用途分工：
- twse_data.py / tpex_data.py → 現貨市場（個股），支撐三大生態選股的三個條件
- taifex_data.py → 期貨市場（大盤整體），只用來顯示「今天大盤氣氛」的參考卡片，
  不影響、也不會混進選股邏輯——選股邏輯的三個條件維持不變。

跟證交所分點系統（bsr.twse.com.tw）不同，這兩支端點是純 POST 表單查詢，
沒有圖形驗證碼，頁面上也沒有「不得散布販售」這類警語，實測（見開發紀錄）
用一般的 requests.post() 就能拿到資料，不需要任何登入或驗證步驟。

【重要】這仍然是收盤後才會有的資料，不是即時盤中報價：
實測台灣時間開盤前查「今天」的期貨行情，回傳的還是前一個交易日的舊資料，
跟 twse_data.py 的情況一樣，早上查跟晚上查拿到的是同一批。這裡沒有假裝
提供即時大盤情緒，只是把「收盤後大盤氣氛」這個新維度也做到跟現貨一樣
老實揭露資料日期。

技術細節（跟 twse_data.py 不同、容易踩雷的地方）：
- 兩支端點的商品代碼命名不一致：期貨行情查詢用 "TX"（大寫兩碼），
  三大法人未平倉查詢用 "TXF"（大寫三碼加 F），兩邊已用真實請求驗證過，
  不能互換。
- 三大法人未平倉報表的 HTML 用的是大寫 <TD>/<TR> 標籤（舊系統遺留），
  跟期貨行情表的小寫標籤不一樣，清洗時對標籤大小寫要用忽略大小寫比對，
  不然 regex 會抓到 0 筆資料（開發時踩過這個坑，已修正）。
- 三大法人報表裡「投信」「外資」兩列不會重複列出商品名稱，只有每個
  商品的第一列（自營商）才有序號跟商品名稱，後面兩列要沿用上一列的
  商品名稱，清洗邏輯要處理這個「延續前一列」的狀態。
"""

import logging
import re
import time
from datetime import date
from typing import Optional

import requests

logger = logging.getLogger("taiwan_stock_scanner")

REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 0.2
USER_AGENT = "Mozilla/5.0"
RETRY_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 1.5

# 台指期在「期貨每日交易行情查詢」用的商品代碼（跟未平倉報表的代碼不同，見檔案開頭說明）
TAIEX_FUTURES_COMMODITY_ID = "TX"
# 台指期在「三大法人未平倉」報表用的商品代碼
TAIEX_FUTURES_INSTITUTIONAL_ID = "TXF"
TAIEX_FUTURES_PRODUCT_NAME = "臺股期貨"

INVESTMENT_TRUST_NAME = "投信"
FOREIGN_INVESTOR_NAME = "外資"
DEALER_NAME = "自營商"


def _clean_number(value) -> Optional[float]:
    """
    把「12,345」「▲1,040」「▼2.32%」「-」這種常見字串數字清成 float，清不出來就回 None。
    TAIFEX 用「▲/▼」符號表示漲跌方向、不會額外加負號，「▼」要自己轉成負數，
    不然下跌的交易日會被誤判成正數（方向直接反過來，這裡務必處理對）。
    """
    if value is None:
        return None
    text = str(value).strip()
    is_down = "▼" in text
    text = text.replace(",", "").replace("▲", "").replace("▼", "").replace("%", "").strip()
    if text in ("", "-", "--", "N/A"):
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return -abs(number) if is_down else number


def _post(url: str, data: dict) -> Optional[str]:
    """
    統一的 TAIFEX POST 請求函式。任何失敗都只記錄 log、回傳 None，不會讓呼叫端當機。
    這兩支端點目前沒觀察到 twse_data.py/tpex_data.py 遇過的暫時性 5xx，
    但還是比照同一套重試邏輯，行為一致、之後好維護。
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.post(
                url, data=data, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"  # 頁面宣告 big5，但實測回應本體是 utf-8，見檔案開頭說明
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"[TAIFEX] 呼叫 {url} 發生錯誤，第 {attempt}/{RETRY_ATTEMPTS} 次嘗試：{e}")
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.error(f"[TAIFEX] 呼叫 {url} 重試 {RETRY_ATTEMPTS} 次後仍失敗，放棄：{last_error}")
    return None


def fetch_futures_daily(target_date: date, commodity_id: str = TAIEX_FUTURES_COMMODITY_ID) -> Optional[dict]:
    """
    抓「單一交易日」期貨每日交易行情，只取近月合約（到期月份最近的那一列，
    交易量最大、最能代表當下市場氣氛）。非交易日或查無資料回傳 None。

    回傳欄位：contract / expiry_month / open / high / low / close /
    change / change_percent / volume / open_interest / settlement_price
    """
    date_str = target_date.strftime("%Y/%m/%d")
    html = _post(
        "https://www.taifex.com.tw/cht/3/futDailyMarketReport",
        {"queryType": "2", "marketCode": "0", "dateaddcnt": "", "commodity_id": commodity_id, "queryDate": date_str},
    )
    if not html:
        return None

    m = re.search(r'<table[^>]*class="table_f[^"]*"[^>]*>.*?</table>', html, re.S)
    if not m:
        return None

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(clean) < 13 or clean[0] != commodity_id:
            continue
        # 欄位順序（已用真實請求驗證過，見檔案開頭說明）：
        # 契約, 到期月份, 開盤價, 最高價, 最低價, 最後成交價, 漲跌價, 漲跌%,
        # 盤後成交量, 一般成交量, 合計成交量, 結算價, 未沖銷契約量
        return {
            "contract": clean[0],
            "expiry_month": clean[1],
            "open": _clean_number(clean[2]),
            "high": _clean_number(clean[3]),
            "low": _clean_number(clean[4]),
            "close": _clean_number(clean[5]),
            "change": _clean_number(clean[6]),
            "change_percent": _clean_number(clean[7]),
            "volume": _clean_number(clean[10]),
            "settlement_price": _clean_number(clean[11]),
            "open_interest": _clean_number(clean[12]),
            "date": target_date.isoformat(),
        }
    return None  # 該日沒有近月合約資料（例如非交易日）


def fetch_institutional_futures_positions(
    target_date: date, commodity_id: str = TAIEX_FUTURES_INSTITUTIONAL_ID
) -> Optional[dict]:
    """
    抓「單一交易日」三大法人（自營商/投信/外資）在台指期的多空未平倉部位，
    只取「臺股期貨」這個商品。市場最常引用的「外資期貨未平倉淨口數」，
    就是這裡外資那一列的「未平倉多空淨額口數」。非交易日或查無資料回傳 None。

    回傳：{"自營商": {...}, "投信": {...}, "外資": {...}}，每個身份別底下是
    {net_position, net_position_amount, long_position, short_position}
    （position 單位是口，amount 單位是元）
    """
    date_str = target_date.strftime("%Y/%m/%d")
    html = _post(
        "https://www.taifex.com.tw/cht/3/futContractsDate",
        {"queryType": "1", "goDay": "", "doQuery": "1", "dateaddcnt": "", "queryDate": date_str, "commodityId": commodity_id},
    )
    if not html:
        return None

    m = re.search(r"<table[^>]*>((?:(?!</table>).)*?期貨合計(?:(?!</table>).)*?)</table>", html, re.S | re.I)
    if not m:
        return None

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S | re.I)
    result: dict = {}
    current_product: Optional[str] = None
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        clean = [re.sub(r"\s+", "", c) for c in clean]
        if not clean:
            continue

        # 每個商品第一列（自營商）帶序號＋商品名稱；投信/外資兩列沿用同一個商品名稱，
        # 見檔案開頭說明。序號欄位是純數字字串，用這個判斷是不是新商品的開始。
        if clean[0].isdigit() and len(clean) >= 15:
            current_product, identity, values = clean[1], clean[2], clean[3:15]
        elif clean[0] in (DEALER_NAME, INVESTMENT_TRUST_NAME, FOREIGN_INVESTOR_NAME) and len(clean) >= 13:
            identity, values = clean[0], clean[1:13]
        else:
            continue  # 期貨小計／期貨合計等彙總列，不是我們要的個別商品列

        if current_product != TAIEX_FUTURES_PRODUCT_NAME:
            continue

        # values 欄位順序：多方口數, 多方金額, 空方口數, 空方金額, 多空淨額口數, 多空淨額金額,
        # 未平倉多方口數, 未平倉多方金額, 未平倉空方口數, 未平倉空方金額, 未平倉多空淨額口數, 未平倉多空淨額金額
        result[identity] = {
            "long_position": _clean_number(values[6]),
            "short_position": _clean_number(values[8]),
            "net_position": _clean_number(values[10]),
            "net_position_amount": _clean_number(values[11]),
        }

    if not result:
        return None
    result["date"] = target_date.isoformat()
    return result
