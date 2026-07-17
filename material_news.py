"""
material_news.py — 上市櫃公司重大訊息公告：利多／利空／重要程度分類
============================================================
資料源是 TWSE／TPEx 官方「重大訊息」開放資料——上市櫃公司依法必須公告
的第一手事實（更名、財報、重大合約、併購、終止上市櫃等），不是新聞媒體
報導。這是刻意的選擇：主要財經新聞網站（Goodinfo、Yahoo股市、經濟日報、
自由時報…）的 robots.txt 都明確擋掉 AI 爬蟲（部分甚至點名 ClaudeBot／
anthropic-ai），這裡改用政府開放資料，沒有這個問題，資料也更原始可信
（公司自己依法揭露的事實，不是媒體加工下標過的二手報導）。

分類邏輯：AI（OpenAI／Gemini，跟 chat_assistant.py 同一套三層架構＋
同一組 .env 金鑰，只是任務不同）把每則公告判斷成利多／利空／中性＋
重要程度 1-5。兩個 API 金鑰都沒設定時，退回規則式關鍵字分類——不是
真正理解語意，但至少能動，不會因為沒金鑰就讓整個功能打不開。
"""

import json
import logging
import os
import re
import time
from typing import Optional

import requests

logger = logging.getLogger("taiwan_stock_scanner")

REQUEST_TIMEOUT = 20
CLASSIFY_TIMEOUT = 60
BATCH_SIZE = 10  # 一次送給 AI 分類幾則公告；太多筆容易被截斷、逾時，或模型把長得很像的兩則公告合併成一則


def _get_openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "")


def _get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _get_gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def _get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def fetch_material_news() -> list:
    """
    抓 TWSE + TPEx 官方重大訊息公告。兩邊回傳的欄位名稱不一樣（TWSE 用
    中文鍵、TPEx 混用英文鍵），這裡對齊成統一格式。任何一邊失敗只記錄
    log、跳過那一邊，不會讓另一邊也抓不到。
    """
    results = []

    try:
        resp = requests.get(
            "https://openapi.twse.com.tw/v1/opendata/t187ap04_L", timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        for row in resp.json():
            subject = (row.get("主旨 ") or row.get("主旨") or "").strip()
            results.append(
                {
                    "market": "上市",
                    "stock_id": str(row.get("公司代號", "")).strip(),
                    "stock_name": str(row.get("公司名稱", "")).strip(),
                    "subject": subject,
                    "detail": (row.get("說明") or "").strip(),
                    "announced_date": row.get("發言日期"),
                    "announced_time": row.get("發言時間"),
                }
            )
    except Exception as e:
        logger.warning(f"[重大訊息] 抓 TWSE 失敗：{e}")

    try:
        resp = requests.get(
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O", timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        for row in resp.json():
            results.append(
                {
                    "market": "上櫃",
                    "stock_id": str(row.get("SecuritiesCompanyCode", "")).strip(),
                    "stock_name": str(row.get("CompanyName", "")).strip(),
                    "subject": (row.get("主旨") or "").strip(),
                    "detail": (row.get("說明") or "").strip(),
                    "announced_date": row.get("發言日期"),
                    "announced_time": row.get("發言時間"),
                }
            )
    except Exception as e:
        logger.warning(f"[重大訊息] 抓 TPEx 失敗：{e}")

    return [r for r in results if r["stock_id"] and r["subject"]]


CLASSIFY_SYSTEM_PROMPT = """你是台股重大訊息分類專家。你會收到一批上市櫃公司依法公告的重大訊息
（每則都有一個 id 編號、主旨、說明），請針對「每一則」判斷：
1. id：原封不動抄回輸入裡的 id，不要自己重編
2. sentiment：對該公司股價「可能」的影響方向，只能是 "利多"、"利空"、"中性" 三選一
3. importance：重要程度，1(低)到5(高)的整數
4. reason：一句話白話說明為什麼這樣判斷，20字以內，要讓不懂財經術語的人也看得懂

判斷原則：
- 只根據提供的公告文字內容判斷，不要臆測公告以外的資訊，也不要過度延伸解讀
- 常規性、行政性公告（例如公司名稱變更、股東會召集、董事會例行決議）通常是「中性」、重要程度 1-2
- 財報獲利成長、重大訂單／合約、對本公司有利的併購、實施庫藏股、調高財測，通常是「利多」
- 財報虧損擴大、重大訴訟敗訴、終止上市／上櫃、債務違約或跳票、調降財測，通常是「利空」，重要程度較高
- 拿不準的情況，寧可判「中性」，不要為了看起來有內容硬歸類成利多或利空
- 【非常重要】即使有兩則公告內容看起來很像（例如同一家公司同一天發了兩則類似公告），
  也必須各自獨立輸出一筆分類結果，不能合併成一筆、也不能省略任何一個 id

輸出必須是純 JSON 陣列（不要有陣列以外的任何文字、不要用 markdown code block 包住），
陣列長度必須跟輸入的公告則數完全一樣：
[{"id": 0, "sentiment": "利多", "importance": 3, "reason": "..."}, ...]
"""


def _build_batch_prompt(items: list) -> str:
    lines = []
    for i, item in enumerate(items):
        detail = item["detail"][:300]  # 說明常常很長，截斷避免 prompt 爆量
        lines.append(f"id={i}\n股票：{item['stock_name']}（{item['stock_id']}）\n主旨：{item['subject']}\n說明：{detail}")
    return "\n\n".join(lines)


def _parse_classification_json(text: str, expected_len: int) -> Optional[list]:
    """
    AI 有時會不小心包一層 ```json 或前後加幾句話，這裡盡量寬容解析。用 id
    對應輸入項目，不是用陣列位置——這樣即使 AI 漏掉某一則或順序跑掉，
    也只有那幾則會補預設值，不會因為個別項目有問題就丟棄整批結果
    （之前用「陣列長度要完全相等」這種嚴格比對，AI 只要把兩則長得很像的
    公告合併成一則、少回傳一筆，整批 10-15 則就全部退回規則式分類，
    正式站實測過這個問題滿常發生，改成用 id 比對容錯）。
    """
    text = text.strip()
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, list):
        return None

    by_id = {}
    for entry in parsed:
        if isinstance(entry, dict) and isinstance(entry.get("id"), int):
            by_id[entry["id"]] = entry

    if not by_id:
        return None

    result = []
    for i in range(expected_len):
        entry = by_id.get(i)
        if entry is None:
            result.append({"sentiment": "中性", "importance": 2, "reason": "AI 分類遺漏，以中性處理"})
        else:
            result.append(entry)
    return result


def _call_openai_classify(items: list) -> Optional[list]:
    api_key = _get_openai_key()
    if not api_key:
        return None
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": _get_openai_model(),
                "messages": [
                    {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_batch_prompt(items)},
                ],
                "temperature": 0.2,
            },
            timeout=CLASSIFY_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return _parse_classification_json(text, len(items))
    except Exception as e:
        logger.warning(f"[重大訊息] OpenAI 分類失敗：{e}")
        return None


def _call_gemini_classify(items: list) -> Optional[list]:
    api_key = _get_gemini_key()
    if not api_key:
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_get_gemini_model()}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": api_key},
            json={
                "systemInstruction": {"parts": [{"text": CLASSIFY_SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": _build_batch_prompt(items)}]}],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=CLASSIFY_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_classification_json(text, len(items))
    except Exception as e:
        logger.warning(f"[重大訊息] Gemini 分類失敗：{e}")
        return None


# 規則式救援分類：兩個 AI 金鑰都沒設定時使用。只用關鍵字比對，不是真的
# 理解語意，但至少能讓功能動起來，也比「完全不分類」有參考價值。
_POSITIVE_KEYWORDS = ["調高", "上修", "訂單增加", "買回庫藏股", "實施庫藏股", "財測上修", "獲利成長", "得標", "中籤", "擴產", "現金股利"]
_NEGATIVE_KEYWORDS = ["調降", "下修", "終止上市", "終止上櫃", "訴訟", "違約", "跳票", "財測下修", "虧損", "裁罰", "存款不足", "重整", "紓困"]
_HIGH_IMPORTANCE_KEYWORDS = ["終止上市", "終止上櫃", "違約", "跳票", "重整", "合併", "併購", "減資", "現金增資", "財測"]


def _fallback_classify(items: list) -> list:
    results = []
    for item in items:
        text = f"{item['subject']} {item['detail']}"
        has_positive = any(kw in text for kw in _POSITIVE_KEYWORDS)
        has_negative = any(kw in text for kw in _NEGATIVE_KEYWORDS)
        if has_negative and not has_positive:
            sentiment = "利空"
        elif has_positive and not has_negative:
            sentiment = "利多"
        else:
            sentiment = "中性"
        importance = 4 if any(kw in text for kw in _HIGH_IMPORTANCE_KEYWORDS) else 2
        results.append({"sentiment": sentiment, "importance": importance, "reason": "系統規則式分類（未設定 AI 金鑰，僅供參考）"})
    return results


def classify_material_news(items: list) -> list:
    """
    幫每一則公告加上 sentiment／importance／reason。分批呼叫 AI（見
    BATCH_SIZE），避免單次 prompt 太長被截斷或逾時。OpenAI 失敗換
    Gemini，兩個都沒設定或都失敗就退回規則式分類，不會讓整個功能掛掉。
    """
    classified = []
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        result = _call_openai_classify(batch)
        source = "openai"
        if result is None:
            result = _call_gemini_classify(batch)
            source = "gemini"
        if result is None:
            result = _fallback_classify(batch)
            source = "fallback"

        for item, cls in zip(batch, result):
            merged = dict(item)
            merged["sentiment"] = cls.get("sentiment", "中性")
            merged["importance"] = cls.get("importance", 2)
            merged["reason"] = cls.get("reason", "")
            merged["classification_source"] = source
            classified.append(merged)

        time.sleep(0.2)  # 對 AI API 也保持禮貌，批次之間留一點間隔

    return classified
