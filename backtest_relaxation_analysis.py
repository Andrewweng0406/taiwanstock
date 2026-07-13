"""比較「三大生態選股」條件放寬後的五年回測表現。

此檔只做研究，不改動網頁的正式策略參數。資料會快取在
``.backtest_data_cache``，之後調整參數時不需重複消耗 FinMind 額度。
"""

import json
import pickle
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

import main


CACHE_DIR = Path(__file__).parent / ".backtest_data_cache"
LOOKBACK_DAYS = 1825
SCENARIOS = {
    "原始嚴格": {"volume": 2.0, "streak": 3, "revenue": 20.0},
    "只放寬量能": {"volume": 1.5, "streak": 3, "revenue": 20.0},
    "只放寬投信": {"volume": 2.0, "streak": 2, "revenue": 20.0},
    "只放寬營收": {"volume": 2.0, "streak": 3, "revenue": 10.0},
    "平衡放寬": {"volume": 1.5, "streak": 2, "revenue": 10.0},
    "積極放寬": {"volume": 1.2, "streak": 1, "revenue": 0.0},
}


def fetch_or_load(stock_id: str, start_dates: dict[str, str], end_date: str):
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"{stock_id}_{start_dates['price']}_{end_date}.pkl"
    if cache_path.exists():
        with cache_path.open("rb") as handle:
            return pickle.load(handle)

    price = main._finmind_get("TaiwanStockPrice", start_dates["price"], end_date, data_id=stock_id)
    inst = main._finmind_get(
        "TaiwanStockInstitutionalInvestorsBuySell", start_dates["inst"], end_date, data_id=stock_id
    )
    if not inst.empty and "name" in inst.columns:
        inst = inst[inst["name"] == main.INVESTMENT_TRUST_NAME]
    revenue = main._finmind_get("TaiwanStockMonthRevenue", start_dates["revenue"], end_date, data_id=stock_id)
    data = (price, inst, revenue)
    with cache_path.open("wb") as handle:
        pickle.dump(data, handle)
    return data


def summarize(frames: list[pd.DataFrame], cutoff: pd.Timestamp) -> dict:
    if not frames:
        return {"signals": 0}
    signals = pd.concat(frames, ignore_index=True)
    signals = signals[pd.to_datetime(signals["signal_date"]) >= cutoff]
    result = {"signals": int(len(signals))}
    for holding in main.BACKTEST_HOLDING_PERIODS:
        values = signals[f"return_{holding}"].dropna()
        wins = values[values > 0]
        losses = values[values <= 0]
        result[str(holding)] = {
            "n": int(len(values)),
            "win_rate": round(float((values > 0).mean() * 100), 1) if len(values) else None,
            "avg_return": round(float(values.mean()), 2) if len(values) else None,
            "median_return": round(float(values.median()), 2) if len(values) else None,
            "profit_factor": round(float(wins.sum() / abs(losses.sum())), 2)
            if len(losses) and losses.sum() != 0
            else None,
        }
    return result


def main_analysis():
    end = date.today()
    starts = {
        "price": (end - timedelta(days=LOOKBACK_DAYS + 40)).isoformat(),
        "inst": (end - timedelta(days=LOOKBACK_DAYS + 10)).isoformat(),
        "revenue": (end - timedelta(days=LOOKBACK_DAYS + 400)).isoformat(),
    }
    raw = {stock_id: fetch_or_load(stock_id, starts, end.isoformat()) for stock_id in main.WATCHLIST}
    cutoff = pd.Timestamp(end - timedelta(days=LOOKBACK_DAYS))
    output = {}
    original = (
        main.VOLUME_MULTIPLIER_THRESHOLD,
        main.INSTITUTIONAL_STREAK_DAYS,
        main.REVENUE_YOY_THRESHOLD,
    )
    try:
        for name, params in SCENARIOS.items():
            main.VOLUME_MULTIPLIER_THRESHOLD = params["volume"]
            main.INSTITUTIONAL_STREAK_DAYS = params["streak"]
            main.REVENUE_YOY_THRESHOLD = params["revenue"]
            frames = []
            for stock_id, (price, inst, revenue) in raw.items():
                frame = main._compute_backtest_signals_for_stock(stock_id, price, inst, revenue)
                if not frame.empty:
                    frames.append(frame)
            output[name] = {"parameters": params, **summarize(frames, cutoff)}
    finally:
        (
            main.VOLUME_MULTIPLIER_THRESHOLD,
            main.INSTITUTIONAL_STREAK_DAYS,
            main.REVENUE_YOY_THRESHOLD,
        ) = original
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main_analysis()
