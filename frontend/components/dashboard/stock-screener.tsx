'use client';

import { useState, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { TermTooltip } from '@/components/ui/term-tooltip';
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

      {!loading && hasScanned && filteredStocks.length > 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          💡 以下是符合三大條件規則篩出來的清單，不是「建議買進」名單。會不會漲、要不要買，
          請自己再做功課判斷；「建議停損價」也只是規則算出來的參考數字，不是保證。
        </p>
      )}

      {/* min-w 讓表格在窄螢幕維持可讀寬度，交給外層 overflow-x-auto 左右滑動，
          不要讓瀏覽器把欄位越擠越窄、文字被迫逐字換行（手機實測過的真實問題） */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead>
            <tr className="border-b border-border bg-card">
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票代號</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票名稱</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">現價</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">
                <span className="flex items-center">
                  量能倍數
                  <TermTooltip explanation="今天成交量是過去 20 天平均成交量的幾倍。倍數越高，代表今天交易特別熱絡，可能有比較多人在關注這檔股票。" />
                </span>
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">
                <span className="flex items-center">
                  營收年增率
                  <TermTooltip explanation="這家公司最新一個月的營業收入，跟去年同一個月比較，成長了百分之幾。正數代表營收在成長。" />
                </span>
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">
                <span className="flex items-center">
                  投信連買天數
                  <TermTooltip explanation="「投信」是三大法人之一（本土基金公司），連續買超代表投信連續好幾天買進這檔股票、沒有賣超，通常被視為法人看好的訊號之一。" />
                </span>
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">
                <span className="flex items-center">
                  建議停損價
                  <TermTooltip explanation="用規則算出來的參考價位（今天開盤價），不是保證線。如果之後股價跌破這個價位，這套規則的邏輯是認賠出場、控制損失，但實際上要不要照做，還是你自己決定。" />
                </span>
              </th>
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
