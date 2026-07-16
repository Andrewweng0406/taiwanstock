'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { DashboardHeader } from '@/components/dashboard/header';
import { TermTooltip } from '@/components/ui/term-tooltip';
import { fetchStockDetail, type StockDetail } from '@/lib/api';
import { getWatchlist, removeFromWatchlist } from '@/lib/watchlist';
import { Star, X } from 'lucide-react';

export default function WatchlistPage() {
  const [stockIds, setStockIds] = useState<string[] | null>(null);
  const [stocks, setStocks] = useState<Record<string, StockDetail>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    setStockIds(getWatchlist());
  }, []);

  useEffect(() => {
    if (!stockIds) return;
    const idsToFetch = stockIds.filter((id) => !stocks[id] && !errors[id] && !loadingIds.has(id));
    if (idsToFetch.length === 0) return;

    setLoadingIds((prev) => new Set([...prev, ...idsToFetch]));
    idsToFetch.forEach((id) => {
      fetchStockDetail(id)
        .then((detail) => {
          if (detail) {
            setStocks((prev) => ({ ...prev, [id]: detail }));
          } else {
            setErrors((prev) => ({ ...prev, [id]: '查無資料' }));
          }
        })
        .catch((err) => {
          setErrors((prev) => ({ ...prev, [id]: err instanceof Error ? err.message : '查詢失敗' }));
        })
        .finally(() => {
          setLoadingIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stockIds]);

  const handleRemove = (stockId: string) => {
    removeFromWatchlist(stockId);
    setStockIds((prev) => (prev ?? []).filter((id) => id !== stockId));
  };

  return (
    <main className="min-h-screen bg-background">
      <DashboardHeader />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8 flex items-center gap-2">
          <Star className="h-6 w-6 fill-amber-400 text-amber-500" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">自選股</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              存在這台裝置的瀏覽器裡，換裝置或清瀏覽器資料會不見；到個股詳情頁按星星圖示可以加入。
            </p>
          </div>
        </div>

        {stockIds !== null && stockIds.length === 0 && (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-muted-foreground">
              還沒有加入任何自選股。到
              <Link href="/" className="mx-1 text-primary underline-offset-2 hover:underline">
                首頁
              </Link>
              搜尋股票，進到詳情頁按星星圖示就能加入。
            </p>
          </div>
        )}

        {stockIds !== null && stockIds.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead>
                <tr className="border-b border-border bg-card">
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票代號</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票名稱</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">現價</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">漲跌幅</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">
                    <span className="flex items-center">
                      資料日期
                      <TermTooltip explanation="現價實際對應的收盤交易日，不是即時盤中報價。" />
                    </span>
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">移除</th>
                </tr>
              </thead>
              <tbody>
                {stockIds.map((id) => {
                  const stock = stocks[id];
                  return (
                    <tr key={id} className="border-b border-border hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3">
                        <Link href={`/stock/${id}`} className="font-semibold text-foreground hover:underline">
                          {id}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {stock ? (
                          <Link href={`/stock/${id}`} className="hover:underline">
                            {stock.stock_name}
                          </Link>
                        ) : errors[id] ? (
                          <span className="text-destructive">{errors[id]}</span>
                        ) : (
                          <span className="text-muted-foreground">載入中…</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {stock ? `NT$${stock.current_price.toFixed(2)}` : '—'}
                      </td>
                      <td className="px-4 py-3">
                        {stock ? (
                          <span className={stock.change >= 0 ? 'text-primary' : 'text-destructive'}>
                            {stock.change >= 0 ? '+' : ''}
                            {stock.change.toFixed(2)}（{stock.change >= 0 ? '+' : ''}
                            {stock.change_percent.toFixed(2)}%）
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{stock ? stock.price_date : '—'}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          aria-label="從自選股移除"
                          onClick={() => handleRemove(id)}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
