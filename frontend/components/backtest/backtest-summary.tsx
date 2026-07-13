import type { BacktestHoldingStat } from '@/lib/api';

interface BacktestSummaryProps {
  summary: Record<string, BacktestHoldingStat | null>;
  holdingPeriods: number[];
}

export function BacktestSummary({ summary, holdingPeriods }: BacktestSummaryProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {holdingPeriods.map((holding) => {
        const stat = summary[String(holding)];
        return (
          <div key={holding} className="rounded-lg border border-border bg-card p-6">
            <p className="text-sm font-medium text-muted-foreground">持有 {holding} 個交易日</p>

            {!stat ? (
              <p className="mt-4 text-sm text-muted-foreground">這個持有期沒有足夠的已滿期訊號</p>
            ) : (
              <>
                <p className="mt-2 text-3xl font-bold text-foreground">{stat.win_rate}%</p>
                <p className="text-xs text-muted-foreground">勝率（{stat.signal_count} 次訊號）</p>

                <div className="mt-4 space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">平均報酬</span>
                    <span
                      className={`font-medium ${stat.avg_return >= 0 ? 'text-primary' : 'text-destructive'}`}
                    >
                      {stat.avg_return >= 0 ? '+' : ''}
                      {stat.avg_return}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">中位數報酬</span>
                    <span className={`font-medium ${stat.median_return >= 0 ? 'text-primary' : 'text-destructive'}`}>
                      {stat.median_return >= 0 ? '+' : ''}{stat.median_return}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">獲利因子</span>
                    <span className="font-medium text-foreground">{stat.profit_factor ?? '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">平均賺（勝）</span>
                    <span className="font-medium text-primary">
                      {stat.avg_win !== null ? `+${stat.avg_win}%` : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">平均賠（敗）</span>
                    <span className="font-medium text-destructive">
                      {stat.avg_loss !== null ? `${stat.avg_loss}%` : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">最佳／最差</span>
                    <span className="font-medium text-foreground">
                      +{stat.best}% / {stat.worst}%
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
