'use client';

import { useState, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import type { ScanResultItem } from '@/lib/api';

interface StockScreenerProps {
  results: ScanResultItem[];
  loading: boolean;
  hasScanned: boolean;
}

type SortKey = 'volume' | 'revenue' | 'buyDays' | 'price';

export function StockScreener({ results, loading, hasScanned }: StockScreenerProps) {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<SortKey>('volume');

  const filteredStocks = useMemo(() => {
    return results
      .filter((stock) => {
        const keyword = search.toLowerCase();
        return (
          stock.stock_id.toLowerCase().includes(keyword) ||
          stock.stock_name.toLowerCase().includes(keyword)
        );
      })
      .sort((a, b) => {
        switch (sortBy) {
          case 'revenue':
            return b.revenue_growth_yoy - a.revenue_growth_yoy;
          case 'buyDays':
            return b.institutional_buy_days - a.institutional_buy_days;
          case 'price':
            return b.current_price - a.current_price;
          case 'volume':
          default:
            return b.volume_multiplier - a.volume_multiplier;
        }
      });
  }, [results, search, sortBy]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-4">選股結果</h2>
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="text-sm font-medium text-foreground">搜尋股票代號或名稱</label>
              <Input
                placeholder="例如：2330、台積電..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="mt-2"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-foreground">排序依據</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortKey)}
                className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
              >
                <option value="volume">量能放大倍數</option>
                <option value="revenue">營收年增率</option>
                <option value="buyDays">投信連買天數</option>
                <option value="price">現價</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-card">
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票代號</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票名稱</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">現價</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">量能倍數</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">營收年增率</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">投信連買天數</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">建議停損價</th>
            </tr>
          </thead>
          <tbody>
            {filteredStocks.map((stock) => (
              <tr
                key={stock.stock_id}
                className="border-b border-border hover:bg-muted/30 transition-colors"
              >
                <td className="px-4 py-3">
                  <p className="font-semibold text-foreground">{stock.stock_id}</p>
                </td>
                <td className="px-4 py-3 text-foreground">{stock.stock_name}</td>
                <td className="px-4 py-3 text-foreground">NT${stock.current_price.toFixed(2)}</td>
                <td className="px-4 py-3">
                  <span className="inline-block rounded bg-primary/10 px-2 py-1 text-sm font-medium text-primary">
                    {stock.volume_multiplier.toFixed(2)}x
                  </span>
                </td>
                <td className="px-4 py-3 font-medium text-primary">
                  {stock.revenue_growth_yoy.toFixed(1)}%
                </td>
                <td className="px-4 py-3 text-foreground">{stock.institutional_buy_days} 天</td>
                <td className="px-4 py-3 text-destructive">NT${stock.stop_loss_price.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {loading && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <p className="text-muted-foreground">全市場掃描中，依資料量可能需要數十秒，請稍候…</p>
        </div>
      )}

      {!loading && hasScanned && filteredStocks.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <p className="text-muted-foreground">
            {results.length === 0
              ? '今天沒有股票同時符合三大條件，明天再來看看。'
              : '沒有符合搜尋條件的股票。'}
          </p>
        </div>
      )}

      {!loading && !hasScanned && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <p className="text-muted-foreground">按下上方「🚀 一鍵掃描全台股」開始掃描。</p>
        </div>
      )}
    </div>
  );
}
