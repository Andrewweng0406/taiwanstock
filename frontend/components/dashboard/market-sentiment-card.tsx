'use client';

import { useEffect, useState } from 'react';
import { TermTooltip } from '@/components/ui/term-tooltip';
import { fetchMarketSentiment, type MarketSentiment } from '@/lib/api';

function formatSignedNumber(value: number | null): string {
  if (value === null) return '—';
  const rounded = Math.round(value);
  return rounded >= 0 ? `+${rounded.toLocaleString()}` : rounded.toLocaleString();
}

function positionTone(netPosition: number | null): string {
  if (netPosition === null) return 'text-muted-foreground';
  return netPosition >= 0 ? 'text-primary' : 'text-destructive';
}

function positionLabel(netPosition: number | null): string {
  if (netPosition === null) return '—';
  return netPosition >= 0 ? '偏多' : '偏空';
}

export function MarketSentimentCard() {
  const [sentiment, setSentiment] = useState<MarketSentiment | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMarketSentiment()
      .then((data) => {
        if (!cancelled) setSentiment(data);
      })
      .catch((err) => {
        if (!cancelled) setErrorMessage(err instanceof Error ? err.message : '查詢大盤情緒時發生未知錯誤');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 查不到資料（連續假期、TAIFEX 服務異常）就整張卡片不顯示，不秀殘缺資料
  if (loading || errorMessage || !sentiment) {
    return null;
  }

  const { futures, foreign_position } = sentiment;

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center text-lg font-semibold text-foreground">
          大盤情緒（台指期）
          <TermTooltip explanation="台指期是用來判斷「整個大盤」方向的參考工具，不是選股用的，跟三大生態選股的三個條件無關。這裡顯示的是最近月份合約的收盤行情，跟三大法人在期貨的多空布局。" />
        </h2>
        <span className="text-xs text-amber-600 dark:text-amber-500">
          ⚠️ 資料截至 {sentiment.trading_date} 收盤，非即時盤中報價
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p className="text-sm text-muted-foreground">
            台指期近月（{futures.expiry_month}）
          </p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-foreground">
              {futures.close !== null ? futures.close.toLocaleString() : '—'}
            </span>
            {futures.change !== null && futures.change_percent !== null && (
              <span className={`text-sm font-semibold ${futures.change >= 0 ? 'text-primary' : 'text-destructive'}`}>
                {futures.change >= 0 ? '+' : ''}
                {futures.change.toLocaleString()}（{futures.change >= 0 ? '+' : ''}
                {futures.change_percent.toFixed(2)}%）
              </span>
            )}
          </div>
        </div>

        <div>
          <p className="flex items-center text-sm text-muted-foreground">
            外資期貨未平倉淨口數
            <TermTooltip explanation="外資在台指期「未平倉」的多方口數減空方口數。正數（偏多）代表外資整體布局偏向看漲大盤，負數（偏空）代表偏向看跌，是市場常拿來判斷法人對大盤看法的參考指標，不是保證。" />
          </p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className={`text-2xl font-bold ${positionTone(foreign_position?.net_position ?? null)}`}>
              {formatSignedNumber(foreign_position?.net_position ?? null)}
            </span>
            <span className={`text-sm font-semibold ${positionTone(foreign_position?.net_position ?? null)}`}>
              {positionLabel(foreign_position?.net_position ?? null)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
