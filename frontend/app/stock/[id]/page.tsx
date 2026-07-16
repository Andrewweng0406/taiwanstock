'use client';

import Link from 'next/link';
import { use, useEffect, useState } from 'react';
import { fetchStockDetail, type StockDetail } from '@/lib/api';
import { StockChart } from '@/components/stock/stock-chart';
import { StockMetrics } from '@/components/stock/stock-metrics';
import { TechnicalIndicators as TechnicalIndicatorsComponent } from '@/components/stock/technical-indicators';
import { RevenueTrend } from '@/components/stock/revenue-trend';
import { InstitutionalRecent } from '@/components/stock/institutional-recent';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Star } from 'lucide-react';
import { isInWatchlist, toggleWatchlist } from '@/lib/watchlist';

export default function StockDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [stock, setStock] = useState<StockDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [watched, setWatched] = useState(false);

  useEffect(() => {
    setWatched(isInWatchlist(id));
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setErrorMessage(null);

    fetchStockDetail(id)
      .then((detail) => {
        if (cancelled) return;
        if (detail === null) {
          setNotFound(true);
        } else {
          setStock(detail);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : '查詢股票資料時發生未知錯誤');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <p className="text-muted-foreground">查詢股票 {id} 的資料中，請稍候…</p>
        </div>
      </div>
    );
  }

  if (notFound || errorMessage || !stock) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-foreground mb-2">
            {notFound ? '找不到這檔股票' : '查詢時發生錯誤'}
          </h1>
          {errorMessage && <p className="mb-4 text-sm text-destructive">{errorMessage}</p>}
          <Link href="/">
            <Button variant="outline">
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回儀表板
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <Link href="/">
        <Button variant="outline" className="mb-6">
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回儀表板
        </Button>
      </Link>

      <div className="mb-8">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-3xl font-bold text-foreground">{stock.stock_name}</h1>
                  <button
                    type="button"
                    aria-label={watched ? '從自選股移除' : '加入自選股'}
                    onClick={() => setWatched(toggleWatchlist(stock.stock_id))}
                    className="text-muted-foreground hover:text-amber-500"
                  >
                    <Star className={`h-6 w-6 ${watched ? 'fill-amber-400 text-amber-500' : ''}`} />
                  </button>
                </div>
                <p className="text-muted-foreground">
                  {stock.stock_id}
                  {stock.industry ? ` · ${stock.industry}` : ''}
                </p>
              </div>
            </div>
            <div className="mt-4 flex items-baseline gap-3">
              <span className="text-4xl font-bold text-foreground">NT${stock.current_price}</span>
              <span
                className={`text-lg font-semibold ${
                  stock.change >= 0 ? 'text-primary' : 'text-destructive'
                }`}
              >
                {stock.change >= 0 ? '+' : ''}
                {stock.change.toFixed(2)} ({stock.change_percent.toFixed(2)}%)
              </span>
            </div>
            <p className="mt-1 text-xs text-amber-600 dark:text-amber-500">
              ⚠️ 資料截至 {stock.price_date} 收盤，為收盤後結算資料，非即時盤中報價
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <div className="rounded-lg border border-border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold text-foreground">股價走勢（近 120 個交易日，K線＋均線）</h2>
            <StockChart data={stock.price_history} />
          </div>
          <RevenueTrend data={stock.revenue_trend} />
          <InstitutionalRecent data={stock.institutional_recent} />
        </div>

        <div className="space-y-6">
          <StockMetrics stock={stock} />
          <TechnicalIndicatorsComponent indicators={stock.technical_indicators} />
        </div>
      </div>
    </div>
  );
}
