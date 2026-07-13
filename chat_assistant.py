"""
chat_assistant.py — AI 選股助理
================================
把 /api/scan 最新一次的掃描結果（今日選股清單）當成背景資料，讓 AI 助理
根據「後端真的算出來的資料」回答使用者的問題，語氣設定成適合長輩／投資
新手閱讀：白話、親切、專業術語要順手翻譯成白話文。

三層架構（由上而下依序嘗試，前一層沒設定金鑰就換下一層，不會因為沒金鑰
就讓整個聊天功能打不開）：
1. OpenAI（設定 OPENAI_API_KEY 才會啟用）
2. Gemini（設定 GEMINI_API_KEY 才會啟用）
3. 本地規則式回覆（fallback，兩個金鑰都沒設定時使用）——直接讀掃描資料，
   用固定模板回答「今天有哪些股票入選」「某檔股票的細節」這類最常見問題。
   不是真正的 AI，但至少能讓整個聊天功能在沒有 API 金鑰的情況下也能動，
   之後想接真正的 LLM，只要在 .env 填一組金鑰，不用改任何程式碼。

如何啟用真正的 AI：
    在專案根目錄的 .env 加一行（擇一）：
        OPENAI_API_KEY=sk-xxxxxxxx
        GEMINI_API_KEY=xxxxxxxx
    存檔後重啟後端即可，不用改程式碼。
"""

import json
import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger("taiwan_stock_scanner")

# 【重要】這幾個金鑰故意不在 import 當下就讀進模組層級常數，而是在每次
# 呼叫時才用 os.getenv() 現讀——因為 main.py 是先 import chat_assistant
# 才呼叫 load_dotenv()，如果在這裡用「模組層級常數 = os.getenv(...)」的
# 寫法，import 當下 .env 根本還沒被載入，會永遠讀到空字串，即使 .env 裡
# 明明有填金鑰，也會被誤判成沒設定、一路退回規則式回覆。踩過這個雷，
# 所以在這支檔案裡固定用函式包起來、呼叫時才讀。
def _get_openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "")


def _get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _get_gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def _get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

REQUEST_TIMEOUT = 30
MAX_SCAN_ITEMS_IN_PROMPT = 20  # 掃描結果太多檔時，只放前 N 檔進 prompt，避免內容太長

SYSTEM_PROMPT = """你是一位親切、有耐心的台股選股助理，主要服務對象是台灣的長輩與投資新手，
這個 App 的設計目標是「全年齡友善」。回答規則：

1. 用語氣溫和、白話文，避免專業術語堆疊。如果一定要用術語（例如「5日均線」
   「爆量」「投信連買」「本益比」），要順手用一句話白話解釋是什麼意思，
   就像跟長輩面對面說明一樣。
2. 讀者可能用放大字體閱讀手機畫面，所以句子不要太長、太多子句，適度分段、
   條列，避免一大段文字擠在一起。
3. 只根據下面提供的「今日選股資料」回答，不要瞎猜或編造股票代號、價格、
   數字。如果使用者問的股票不在資料裡，要老實說「今天的清單裡沒有這一檔，
   可能沒有同時符合三個條件」，不要編造答案。
4. 不要保證獲利、不要說「一定會漲」、不要給明確的買賣建議，可以提醒使用者
   這只是輔助參考，投資有風險，最終決定要自己評估或詢問專業理財顧問。
5. 回答盡量精簡扼要，抓重點講清楚就好，不要長篇大論。
"""


def _build_context_text(scan_context: Optional[dict]) -> str:
    """把掃描結果整理成一段給 AI 讀的白話文字背景資料。"""
    if not scan_context:
        return "（目前沒有任何選股掃描資料，使用者可能還沒按過「一鍵掃描全台股」）"

    data = scan_context.get("data", [])
    lines = [f"【今日選股掃描】掃描時間：{scan_context.get('scan_time', '未知')}，共有 {len(data)} 檔符合三大條件："]

    if not data:
        lines.append("（今天沒有股票同時符合技術面、籌碼面、基本面三個條件，這是正常結果，不代表系統故障）")
    else:
        for item in data[:MAX_SCAN_ITEMS_IN_PROMPT]:
            lines.append(
                f"- 股票代號 {item.get('stock_id')}，股票名稱 {item.get('stock_name')}："
                f"現價 {item.get('current_price')} 元，"
                f"成交量是 20 日均量的 {item.get('volume_multiplier')} 倍，"
                f"投信已連續買超 {item.get('institutional_buy_days')} 天，"
                f"最新月營收年增率 {item.get('revenue_growth_yoy')}%，"
                f"建議停損價（今日開盤價）{item.get('stop_loss_price')} 元"
            )
        if len(data) > MAX_SCAN_ITEMS_IN_PROMPT:
            lines.append(f"（清單還有其他 {len(data) - MAX_SCAN_ITEMS_IN_PROMPT} 檔，因篇幅省略）")

    return "\n".join(lines)


def _call_openai(user_message: str, context_text: str) -> Optional[str]:
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
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"今日選股資料：\n{context_text}\n\n使用者問題：{user_message}"},
                ],
                "temperature": 0.4,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"[AI助理] 呼叫 OpenAI 失敗：{e}")
        return None


def _call_gemini(user_message: str, context_text: str) -> Optional[str]:
    api_key = _get_gemini_key()
    if not api_key:
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_get_gemini_model()}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": api_key},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"今日選股資料：\n{context_text}\n\n使用者問題：{user_message}"}],
                    }
                ],
                "generationConfig": {"temperature": 0.4},
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"[AI助理] 呼叫 Gemini 失敗：{e}")
        return None


def _fallback_reply(user_message: str, scan_context: Optional[dict]) -> str:
    """
    沒有設定任何 API 金鑰時的救援方案：用簡單規則從掃描資料裡找答案。
    不是真正的 AI（不會理解語意、不能閒聊），但能老實根據真實資料回答
    「今天有哪些股票入選」「某檔股票的細節」這兩類最常見的問題。
    """
    data = (scan_context or {}).get("data", [])

    stock_id_match = re.search(r"\b(\d{4})\b", user_message)
    if stock_id_match:
        stock_id = stock_id_match.group(1)
        hit = next((d for d in data if d.get("stock_id") == stock_id), None)
        if hit:
            return (
                f"「{hit.get('stock_name')}」（{stock_id}）今天有入選喔！\n\n"
                f"現在股價是 {hit.get('current_price')} 元。\n"
                f"成交量是平常的 {hit.get('volume_multiplier')} 倍，代表今天買賣特別熱絡"
                f"（這就是「爆量」的意思）。\n"
                f"投信（一種專業機構投資人）已經連續買了 {hit.get('institutional_buy_days')} 天。\n"
                f"最近一個月的營收，比去年同期成長了 {hit.get('revenue_growth_yoy')}%。\n"
                f"建議的停損價是 {hit.get('stop_loss_price')} 元"
                f"（如果股價跌破這裡，可以考慮賣出，保護自己不要虧損太多）。\n\n"
                f"提醒您：這只是輔助參考，投資還是有風險，請自己評估喔！"
            )
        if scan_context is not None:
            # 有掃描過，只是這檔沒入選（可能是 0 檔，也可能是入選了別檔）——
            # 這是正常結果，不是「還沒掃描」，訊息不能誤導使用者去重複按按鈕。
            return f"今天的選股清單裡沒有看到 {stock_id} 這一檔股票，可能它今天沒有同時符合技術面、籌碼面、基本面三個條件。"
        return (
            f"目前還沒有掃描資料，沒辦法確認 {stock_id} 今天符不符合條件。"
            f"請先按上面的「🚀 一鍵掃描全台股」按鈕，掃描完成後再問我一次。"
        )

    if scan_context is None:
        return "目前還沒有掃描資料喔！請先按上面的「🚀 一鍵掃描全台股」按鈕，掃描完成後我就可以根據今天的結果回答您的問題了。"

    if not data:
        return (
            "今天掃描過了，不過沒有股票同時符合技術面、籌碼面、基本面這三個條件喔！\n\n"
            "這是正常的結果，不代表系統出錯——三個條件同時成立本來就比較少見，"
            "明天可以再來看看有沒有新的機會。"
        )

    names = "、".join(f"{d.get('stock_name')}（{d.get('stock_id')}）" for d in data[:10])
    return (
        f"今天總共有 {len(data)} 檔股票同時符合技術面、籌碼面、基本面三個條件，"
        f"前幾檔是：{names}。\n\n"
        f"您可以直接跟我說股票代號（例如「2330 怎麼樣？」），我可以幫您講解細節喔！\n\n"
        f"（小提醒：目前還沒設定 AI 金鑰，我先用簡單的方式回答您；"
        f"如果想要更聰明的問答，可以請工程師在 .env 設定 OPENAI_API_KEY 或 GEMINI_API_KEY）"
    )


def generate_reply(user_message: str, scan_context: Optional[dict] = None) -> dict:
    """
    產生 AI 助理回覆。依序嘗試 OpenAI → Gemini → 本地規則式回覆。
    回傳 {"reply": str, "source": "openai" | "gemini" | "fallback"}。
    """
    user_message = (user_message or "").strip()
    if not user_message:
        return {"reply": "請輸入您的問題喔，例如「今天有哪些股票入選？」或「2330 怎麼樣？」", "source": "fallback"}

    context_text = _build_context_text(scan_context)

    reply = _call_openai(user_message, context_text)
    if reply:
        return {"reply": reply.strip(), "source": "openai"}

    reply = _call_gemini(user_message, context_text)
    if reply:
        return {"reply": reply.strip(), "source": "gemini"}

    return {"reply": _fallback_reply(user_message, scan_context), "source": "fallback"}
