"""用 TWSE／TPEx 官方資料建立研究用中小型股清單。"""

import json
from pathlib import Path

import pandas as pd

import main
import tpex_data
import twse_data


OUTPUT = Path(__file__).parent / "small_cap_watchlist.json"
TARGET_COUNT = 100
MIN_MEDIAN_DAILY_VALUE = 10_000_000  # 近20日每日成交金額中位數至少1,000萬元


def build():
    capital = pd.concat(
        [twse_data.fetch_capital_all(), tpex_data.fetch_capital_all()], ignore_index=True
    )
    capital = capital.dropna(subset=["stock_id", "capital"])
    capital = capital[capital["capital"] < main.CAPITAL_LIMIT]

    prices = main._fetch_market_ohlc_all_markets(lookback_calendar_days=40)
    prices = prices.dropna(subset=["stock_id", "close", "Trading_Volume"]).copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["traded_value"] = prices["close"] * prices["Trading_Volume"]
    # 只用每檔最新20個交易日，避免停牌／缺日造成不一致。
    prices = prices.sort_values(["stock_id", "date"]).groupby("stock_id").tail(20)
    liquidity = prices.groupby("stock_id").agg(
        median_daily_value=("traded_value", "median"),
        trading_days=("date", "nunique"),
        latest_close=("close", "last"),
    ).reset_index()
    names = prices.sort_values("date").groupby("stock_id").tail(1)[["stock_id", "stock_name"]]
    candidates = capital.merge(liquidity, on="stock_id", how="inner").merge(names, on="stock_id", how="left")
    candidates = candidates[
        (candidates["trading_days"] >= 15)
        & (candidates["median_daily_value"] >= MIN_MEDIAN_DAILY_VALUE)
    ].sort_values(["median_daily_value", "stock_id"], ascending=[False, True]).head(TARGET_COUNT)

    records = []
    for row in candidates.itertuples():
        records.append(
            {
                "stock_id": row.stock_id,
                "stock_name": row.stock_name,
                "capital": round(float(row.capital)),
                "median_daily_value": round(float(row.median_daily_value)),
                "trading_days": int(row.trading_days),
            }
        )
    payload = {
        "method": "current capital < 4bn NTD; top 100 by 20-day median traded value",
        "minimum_median_daily_value": MIN_MEDIAN_DAILY_VALUE,
        "count": len(records),
        "data": records,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(records), "lowest_median_daily_value": records[-1]["median_daily_value"] if records else None}, ensure_ascii=False))


if __name__ == "__main__":
    build()
