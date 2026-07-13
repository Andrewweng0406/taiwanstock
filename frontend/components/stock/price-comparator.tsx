'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { fetchStockDetail, type StockDetail } from '@/lib/api';

// 快速選取清單：常見權值股，方便使用者一鍵加入比較，不用自己打代號。
const QUICK_PICKS = [
  { id: '2330', label: '台積電' },
  { id: '2317', label: '鴻海' },
  { id: '2454', label: '聯發科' },
  { id: '2382', label: '廣達' },
  { id: '2308', label: '台達電' },
  { id: '3008', label: '大立光' },
  { id: '2412', label: '中華電' },
  { id: '2883', label: '開發金' },
];

const MAX_SELECTED = 3;

function formatMarketCap(value: number | null): string {
  if (value === null) return '—';
  if (value >= 1_000_000_000_000) return (value / 1_000_000_000_000).toFixed(2) + '兆';
  return (value / 100_000_000).toFixed(1) + '億';
}

function formatNumber(value: number | null, digits = 2): string {
  return value === null ? '—' : value.toFixed(digits);
}

export function PriceComparator() {
  const [selectedIds, setSelectedIds] = useState<string[]>(['2330', '2454']);
  const [stocks, setStocks] = useState<Record<string, StockDetail>>({});
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});

  const toggleStock = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id].slice(-MAX_SELECTED)
    );
  };

  // 每次選取清單變動時，把還沒查過、也不在查詢中的股票代號送出查詢。
  // 已經查過（成功或失敗）的代號不會重複打 API。
  useEffect(() => {
    const idsToFetch = selectedIds.filter(
      (id) => !stocks[id] && !errors[id] && !loadingIds.has(id)
    );
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
  }, [selectedIds]);

  const metricRows: Array<{ label: string; render: (s: StockDetail) => string }> = [
    { label: '現價', render: (s) => `NT$${s.current_price.toFixed(2)}` },
    {
      label: '漲跌幅',
      render: (s) => `${s.change_percent >= 0 ? '+' : ''}${s.change_percent.toFixed(2)}%`,
    },
    { label: '本益比', render: (s) => formatNumber(s.pe) },
    { label: '股價淨值比', render: (s) => formatNumber(s.pb) },
    { label: '殖利率', render: (s) => (s.dividend_yield === null ? '—' : `${s.dividend_yield.toFixed(2)}%`) },
    { label: '市值', render: (s) => formatMarketCap(s.market_cap) },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-4 text-lg font-semibold text-foreground">股票比較</h2>
        <div className="flex flex-wrap gap-2 rounded-lg border border-border bg-card p-4">
          {QUICK_PICKS.map((pick) => (
            <Button
              key={pick.id}
              variant={selectedIds.includes(pick.id) ? 'default' : 'outline'}
              size="sm"
              onClick={() => toggleStock(pick.id)}
            >
              {pick.label}
            </Button>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">最多可選擇 {MAX_SELECTED} 檔股票比較</p>
      </div>

      {selectedIds.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">指標</th>
                {selectedIds.map((id) => (
                  <th key={id} className="px-4 py-3 text-left text-sm font-semibold text-foreground">
                    {stocks[id]?.stock_name ?? id}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metricRows.map((row) => (
                <tr key={row.label} className="border-b border-border hover:bg-muted/30">
                  <td className="px-4 py-3 text-sm font-medium text-muted-foreground">{row.label}</td>
                  {selectedIds.map((id) => (
                    <td key={`${id}-${row.label}`} className="px-4 py-3 text-sm text-foreground">
                      {stocks[id] ? (
                        row.render(stocks[id])
                      ) : errors[id] ? (
                        <span className="text-destructive">{errors[id]}</span>
                      ) : (
                        <span className="text-muted-foreground">載入中…</span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
