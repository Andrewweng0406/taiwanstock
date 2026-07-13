import type { StockDetail } from '@/lib/api';

interface StockMetricsProps {
  stock: StockDetail;
}

function formatCurrency(value: number | null): string {
  if (value === null) return '—';
  if (value >= 1_000_000_000_000) return 'NT$' + (value / 1_000_000_000_000).toFixed(2) + '兆';
  if (value >= 100_000_000) return 'NT$' + (value / 100_000_000).toFixed(1) + '億';
  return 'NT$' + value.toLocaleString();
}

function formatNumber(value: number | null, digits = 2): string {
  return value === null ? '—' : value.toFixed(digits);
}

export function StockMetrics({ stock }: StockMetricsProps) {
  const metrics = [
    { label: '市值', value: formatCurrency(stock.market_cap) },
    { label: '股本', value: formatCurrency(stock.capital) },
    { label: '成交量', value: (stock.volume / 1000).toFixed(0) + ' 張' },
    { label: '均量（20日）', value: stock.volume_avg !== null ? (stock.volume_avg / 1000).toFixed(0) + ' 張' : '—' },
    { label: '本益比', value: formatNumber(stock.pe) },
    { label: '股價淨值比', value: formatNumber(stock.pb) },
    { label: '殖利率', value: stock.dividend_yield !== null ? formatNumber(stock.dividend_yield) + '%' : '—' },
  ];

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-4 text-lg font-semibold text-foreground">關鍵指標</h2>
      <div className="space-y-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">{metric.label}</span>
            <span className="font-semibold text-foreground">{metric.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
