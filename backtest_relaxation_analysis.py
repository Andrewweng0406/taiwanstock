"""比較「三大生態選股」條件放寬後的五年回測表現。

此檔只做研究，不改動網頁的正式策略參數。資料會快取在
``.backtest_data_cache``，之後調整參數時不需重複消耗 FinMind 額度。
"""

import json
import os
import pickle
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

import main

# 研究用 token 必須與正式站 .env 分離；未設定就直接停止，
# 避免不小心消耗 main.py 載入的正式 token 額度。
ANALYSIS_TOKEN = os.environ.get("FINMIND_ANALYSIS_TOKEN")
if not ANALYSIS_TOKEN:
    raise RuntimeError("請先設定 FINMIND_ANALYSIS_TOKEN；研究腳本不會使用 .env 的正式 token")
main.API_TOKEN = ANALYSIS_TOKEN


CACHE_DIR = Path(__file__).parent / ".backtest_data_cache"
LOOKBACK_DAYS = 1825
WATCHLIST_FILE = os.environ.get("ANALYSIS_WATCHLIST_FILE")
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
    cached = None
    if cache_path.exists():
        with cache_path.open("rb") as handle:
            cached = pickle.load(handle)
        # API 額度用完時 _finmind_get 會回空表；不可把失敗結果當成有效快取。
        if len(cached) == 3 and all(not frame.empty for frame in cached):
            price, inst, revenue = cached
        else:
            cached = None

    if cached is None:
        price = main._finmind_get("TaiwanStockPrice", start_dates["price"], end_date, data_id=stock_id)
        inst = main._finmind_get(
            "TaiwanStockInstitutionalInvestorsBuySell", start_dates["inst"], end_date, data_id=stock_id
        )
        if not inst.empty and "name" in inst.columns:
            inst = inst[inst["name"] == main.INVESTMENT_TRUST_NAME]
        revenue = main._finmind_get("TaiwanStockMonthRevenue", start_dates["revenue"], end_date, data_id=stock_id)
        data = (price, inst, revenue)
        if all(not frame.empty for frame in data):
            with cache_path.open("wb") as handle:
                pickle.dump(data, handle)

    balance_path = CACHE_DIR / f"{stock_id}_{start_dates['revenue']}_{end_date}_balance.pkl"
    balance = pd.DataFrame()
    if balance_path.exists():
        with balance_path.open("rb") as handle:
            balance = pickle.load(handle)
    if balance.empty:
        balance = main._finmind_get(
            "TaiwanStockBalanceSheet", start_dates["revenue"], end_date, data_id=stock_id
        )
        if not balance.empty:
            with balance_path.open("wb") as handle:
                pickle.dump(balance, handle)
    return price, inst, revenue, balance


def apply_historical_capital_filter(signals: pd.DataFrame, balance: pd.DataFrame) -> pd.DataFrame:
    """只留訊號當時已公開的最近一期股本 < 40 億。

    FinMind 資產負債表的 date 是期末日而非公告日；研究口徑對
    Q1/Q2/Q3 延後 60 天、年報延後 90 天，不提前使用未公開資訊。
    """
    if signals.empty or balance.empty:
        return pd.DataFrame(columns=signals.columns)
    # 一般產業使用 CapitalStock；金融業報表只提供 OrdinaryShare。
    # 同期兩者都有時以 CapitalStock（股本合計）優先。
    capital = balance[balance["type"].isin(["CapitalStock", "OrdinaryShare"])][
        ["date", "type", "value"]
    ].copy()
    if capital.empty:
        return pd.DataFrame(columns=signals.columns)
    capital["type_priority"] = capital["type"].map({"OrdinaryShare": 0, "CapitalStock": 1})
    capital = capital.sort_values(["date", "type_priority"]).drop_duplicates("date", keep="last")
    capital["report_date"] = pd.to_datetime(capital["date"])
    capital["effective_date"] = capital["report_date"] + capital["report_date"].dt.month.map(
        lambda month: pd.Timedelta(days=90 if month == 12 else 60)
    )
    capital = capital.sort_values("effective_date").drop_duplicates("effective_date", keep="last")
    candidates = signals.copy()
    candidates["signal_date_dt"] = pd.to_datetime(candidates["signal_date"])
    merged = pd.merge_asof(
        candidates.sort_values("signal_date_dt"),
        capital[["effective_date", "value"]].sort_values("effective_date"),
        left_on="signal_date_dt",
        right_on="effective_date",
        direction="backward",
    )
    return merged[merged["value"] < main.CAPITAL_LIMIT].drop(
        columns=["signal_date_dt", "effective_date", "value"]
    )


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
    if WATCHLIST_FILE:
        payload = json.loads(Path(WATCHLIST_FILE).read_text(encoding="utf-8"))
        watchlist = [row["stock_id"] for row in payload["data"]]
    else:
        watchlist = main.WATCHLIST
    raw = {stock_id: fetch_or_load(stock_id, starts, end.isoformat()) for stock_id in watchlist}
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
            for stock_id, (price, inst, revenue, balance) in raw.items():
                frame = main._compute_backtest_signals_for_stock(stock_id, price, inst, revenue)
                frame = apply_historical_capital_filter(frame, balance)
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
