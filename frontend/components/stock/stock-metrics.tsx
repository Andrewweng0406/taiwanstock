import type { StockDetail } from '@/lib/api';
import { TermTooltip } from '@/components/ui/term-tooltip';

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
  const metrics: Array<{ label: string; value: string; explanation?: string }> = [
    { label: '市值', value: formatCurrency(stock.market_cap), explanation: '這家公司值多少錢＝股價 × 在外流通股數，數字越大代表公司規模越大。' },
    { label: '股本', value: formatCurrency(stock.capital), explanation: '公司當初股東實際出的錢（實收資本額），股本越小，股價越容易被少量資金拉動、波動也可能越大。' },
    { label: '成交量', value: (stock.volume / 1000).toFixed(0) + ' 張' },
    { label: '均量（20日）', value: stock.volume_avg !== null ? (stock.volume_avg / 1000).toFixed(0) + ' 張' : '—', explanation: '最近 20 個交易日平均每天成交幾張，用來當「正常量」的基準，今天量能有沒有異常放大，就是跟這個比。' },
    { label: '本益比', value: formatNumber(stock.pe), explanation: '股價 ÷ 每股賺的錢，數字越低代表用比較便宜的價格買到這家公司的獲利，但也要看同產業水準才有意義，不是越低越好。' },
    { label: '股價淨值比', value: formatNumber(stock.pb), explanation: '股價 ÷ 每股淨值（公司帳上資產減負債後，換算成每股的價值），大於 1 代表市場願意付比帳面價值更高的價錢買這家公司。' },
    { label: '殖利率', value: stock.dividend_yield !== null ? formatNumber(stock.dividend_yield) + '%' : '—', explanation: '每年配發的股息，占目前股價的比例。可以理解成「用現在的價格買，每年大概能領到多少比例的現金股息」。' },
  ];

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-4 text-lg font-semibold text-foreground">關鍵指標</h2>
      <div className="space-y-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="flex items-center justify-between">
            <span className="flex items-center text-sm text-muted-foreground">
              {metric.label}
              {metric.explanation && <TermTooltip explanation={metric.explanation} />}
            </span>
            <span className="font-semibold text-foreground">{metric.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
