import type { TechnicalIndicators as TechnicalIndicatorsType } from '@/lib/api';
import { TermTooltip } from '@/components/ui/term-tooltip';

interface TechnicalIndicatorsProps {
  indicators: TechnicalIndicatorsType;
}

function fmt(value: number | null, digits = 2): string {
  return value === null ? '—' : value.toFixed(digits);
}

export function TechnicalIndicators({ indicators }: TechnicalIndicatorsProps) {
  const getRSIStatus = (rsi: number | null) => {
    if (rsi === null) return { label: '資料不足', color: 'text-muted-foreground' };
    if (rsi > 70) return { label: '超買', color: 'text-destructive' };
    if (rsi < 30) return { label: '超賣', color: 'text-primary' };
    return { label: '中性', color: 'text-muted-foreground' };
  };

  const getMACDStatus = (histogram: number | null) => {
    if (histogram === null) return { label: '資料不足', color: 'text-muted-foreground' };
    if (histogram > 0) return { label: '偏多', color: 'text-primary' };
    if (histogram < 0) return { label: '偏空', color: 'text-destructive' };
    return { label: '中性', color: 'text-muted-foreground' };
  };

  const rsiStatus = getRSIStatus(indicators.rsi);
  const macdStatus = getMACDStatus(indicators.histogram);

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-4 text-lg font-semibold text-foreground">技術指標</h2>
      <div className="space-y-5">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="flex items-center text-sm text-muted-foreground">
              RSI（14）
              <TermTooltip explanation="衡量最近 14 天漲跌力道的指標，0-100 之間。數字太高（超過 70）代表短期漲太快、可能有回檔壓力；太低（低於 30）代表跌太多、可能有反彈機會。" />
            </span>
            <span className={`text-sm font-semibold ${rsiStatus.color}`}>{rsiStatus.label}</span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${Math.min(indicators.rsi ?? 0, 100)}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{fmt(indicators.rsi)}</p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="flex items-center text-sm text-muted-foreground">
              MACD
              <TermTooltip explanation="用兩條移動平均線的差距，判斷趨勢方向跟強弱的指標。柱狀圖是正的（偏多）代表短期動能偏強，是負的（偏空）代表動能偏弱，不是直接的買賣訊號，是輔助判斷用的。" />
            </span>
            <span className={`text-sm font-semibold ${macdStatus.color}`}>{macdStatus.label}</span>
          </div>
          <div className="space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">MACD 線：</span>
              <span className="font-medium text-foreground">{fmt(indicators.macd, 4)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">訊號線：</span>
              <span className="font-medium text-foreground">{fmt(indicators.signal, 4)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">柱狀圖：</span>
              <span className={`font-medium ${macdStatus.color}`}>{fmt(indicators.histogram, 4)}</span>
            </div>
          </div>
        </div>

        <div>
          <h3 className="mb-3 flex items-center text-sm font-semibold text-foreground">
            移動平均線
            <TermTooltip explanation="最近 N 天收盤價的平均值，用來看趨勢：股價站上均線，通常代表短期偏強；跌破均線，通常代表短期偏弱。20 天約等於 1 個月、200 天約等於 1 年的交易日。" />
          </h3>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">MA(20)：</span>
              <span className="font-medium text-foreground">NT${fmt(indicators.ma20)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">MA(50)：</span>
              <span className="font-medium text-foreground">NT${fmt(indicators.ma50)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">MA(200)：</span>
              <span className="font-medium text-foreground">NT${fmt(indicators.ma200)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
