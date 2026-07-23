"""Record forward paper-trading signals for the locked research strategy.

This script does not place orders and does not change production constants on disk.
It temporarily applies the locked research parameters at runtime, scans the current
official TWSE/TPEx market data, and appends new signals to a local JSONL ledger.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import main


ROOT = Path(__file__).parent
# 這支腳本的整個目的是累積 3-6 個月的紙上交易訊號（見 STRATEGY_RESEARCH_REPORT.md
# 第9節），但 Railway 的容器預設是每次重新部署就換一個全新的檔案系統——實測
# 發現 paper_trade_ledger.jsonl 會因為（跟這個研究完全無關的）正式站功能部署
# 而被整個洗掉，等於紙上交易資料一直沒有真的累積起來。DATA_DIR 環境變數指到
# Railway 掛的持久化 volume（/data），部署再多次也不會影響裡面的檔案；本機
# 開發沒設這個環境變數時，預設還是寫在專案資料夾，行為跟以前一樣。
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT))
LEDGER_FILE = DATA_DIR / "paper_trade_ledger.jsonl"
LATEST_FILE = DATA_DIR / "paper_trade_latest.json"

LOCKED_VOLUME_MULTIPLIER = 1.5
LOCKED_INSTITUTIONAL_DAYS = 3
LOCKED_REVENUE_YOY = 20.0
LOCKED_ATR_MULTIPLE = 2.0
LOCKED_MAX_HOLDING_DAYS = 20


def _read_ledger_keys() -> set[tuple[str, str]]:
    if not LEDGER_FILE.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    with LEDGER_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            keys.add((str(row.get("signal_date")), str(row.get("stock_id"))))
    return keys


def _load_scan_cache() -> tuple[str, list[dict[str, Any]], str | None]:
    cache = main._load_scan_cache()
    if cache is None:
        raise RuntimeError("No valid latest_scan_result.json cache found. Run without --from-cache to scan.")
    return cache["trading_date"], cache.get("data", []), cache.get("scan_time")


def _calculate_atr_snapshot(trading_date: str, stock_ids: set[str]) -> dict[str, dict[str, float]]:
    if not stock_ids:
        return {}
    market = main._fetch_market_ohlc_all_markets(lookback_calendar_days=45)
    if market.empty:
        return {}
    market["stock_id"] = market["stock_id"].astype(str)
    market["date"] = pd.to_datetime(market["date"])
    target = pd.Timestamp(trading_date)
    snapshots: dict[str, dict[str, float]] = {}
    for stock_id, frame in market[market["stock_id"].isin(stock_ids)].groupby("stock_id"):
        frame = frame.sort_values("date").drop_duplicates("date", keep="last").copy()
        if len(frame) < 15:
            continue
        previous_close = frame["close"].shift(1)
        true_range = pd.concat(
            [
                frame["max"] - frame["min"],
                (frame["max"] - previous_close).abs(),
                (frame["min"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr14"] = true_range.rolling(14).mean()
        row = frame[frame["date"] == target]
        if row.empty or pd.isna(row.iloc[-1]["atr14"]):
            continue
        latest = row.iloc[-1]
        close = float(latest["close"])
        atr14 = float(latest["atr14"])
        snapshots[stock_id] = {
            "signal_close": close,
            "atr14": atr14,
            "preliminary_2atr_stop_from_close": round(close - LOCKED_ATR_MULTIPLE * atr14, 2),
            "signal_low": float(latest["min"]),
        }
    return snapshots


def _scan_locked_strategy(from_cache: bool) -> tuple[str, list[dict[str, Any]], str | None]:
    if from_cache:
        return _load_scan_cache()

    original = (
        main.VOLUME_MULTIPLIER_THRESHOLD,
        main.INSTITUTIONAL_STREAK_DAYS,
        main.REVENUE_YOY_THRESHOLD,
    )
    try:
        main.VOLUME_MULTIPLIER_THRESHOLD = LOCKED_VOLUME_MULTIPLIER
        main.INSTITUTIONAL_STREAK_DAYS = LOCKED_INSTITUTIONAL_DAYS
        main.REVENUE_YOY_THRESHOLD = LOCKED_REVENUE_YOY
        trading_date, results = main.run_full_scan()
        return trading_date, results, None
    finally:
        (
            main.VOLUME_MULTIPLIER_THRESHOLD,
            main.INSTITUTIONAL_STREAK_DAYS,
            main.REVENUE_YOY_THRESHOLD,
        ) = original


def run(from_cache: bool = False) -> dict[str, Any]:
    trading_date, results, cache_time = _scan_locked_strategy(from_cache)
    now = datetime.now().isoformat(timespec="seconds")
    existing = _read_ledger_keys()
    atr = _calculate_atr_snapshot(trading_date, {str(row["stock_id"]) for row in results})

    new_records = []
    for row in results:
        stock_id = str(row["stock_id"])
        key = (trading_date, stock_id)
        if key in existing:
            continue
        atr_row = atr.get(stock_id, {})
        record = {
            "status": "signal_logged_pending_next_open",
            "recorded_at": now,
            "signal_date": trading_date,
            "stock_id": stock_id,
            "stock_name": row.get("stock_name"),
            "signal_close": row.get("current_price"),
            "volume_multiplier": row.get("volume_multiplier"),
            "institutional_buy_days": row.get("institutional_buy_days"),
            "revenue_growth_yoy": row.get("revenue_growth_yoy"),
            "locked_strategy": {
                "volume_multiplier_gt": LOCKED_VOLUME_MULTIPLIER,
                "institutional_buy_days_gte": LOCKED_INSTITUTIONAL_DAYS,
                "revenue_yoy_gt": LOCKED_REVENUE_YOY,
                "atr_stop_multiple": LOCKED_ATR_MULTIPLE,
                "max_holding_days": LOCKED_MAX_HOLDING_DAYS,
            },
            "paper_trade_plan": {
                "entry_rule": "next_trading_day_open",
                "stop_rule": "entry_price - 2 * ATR14 from signal date",
                "exit_rule": "stop hit or 20 trading days, whichever comes first",
                "position_sizing": "paper only; suggested model assumption is 10% equity per name, max 10 names",
            },
            "atr14": atr_row.get("atr14"),
            "preliminary_2atr_stop_from_close": atr_row.get("preliminary_2atr_stop_from_close"),
            "signal_low": atr_row.get("signal_low"),
        }
        new_records.append(record)

    if new_records:
        with LEDGER_FILE.open("a", encoding="utf-8") as handle:
            for record in new_records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    payload = {
        "success": True,
        "mode": "from_cache" if from_cache else "fresh_scan",
        "recorded_at": now,
        "scan_cache_time": cache_time,
        "signal_date": trading_date,
        "locked_strategy": {
            "volume_multiplier_gt": LOCKED_VOLUME_MULTIPLIER,
            "institutional_buy_days_gte": LOCKED_INSTITUTIONAL_DAYS,
            "revenue_yoy_gt": LOCKED_REVENUE_YOY,
            "atr_stop_multiple": LOCKED_ATR_MULTIPLE,
            "max_holding_days": LOCKED_MAX_HOLDING_DAYS,
        },
        "signals_found": len(results),
        "new_records_appended": len(new_records),
        "ledger_file": str(LEDGER_FILE),
        "signals": new_records,
    }
    LATEST_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Record locked-strategy paper-trading signals.")
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Use today's latest_scan_result.json instead of running a fresh official-market scan.",
    )
    args = parser.parse_args()
    try:
        payload = run(from_cache=args.from_cache)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        if hasattr(main, "_scan_scheduler") and main._scan_scheduler.running:
            main._scan_scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main_cli()
