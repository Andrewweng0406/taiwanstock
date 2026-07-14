import type { BacktestHoldingStat } from '@/lib/api';
import { TermTooltip } from '@/components/ui/term-tooltip';

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
                <p className="flex items-center text-xs text-muted-foreground">
                  勝率（{stat.signal_count} 次訊號）
                  <TermTooltip explanation="過去符合條件的訊號裡，持有這麼多天之後是賺錢的比例。這是歷史統計數字，不是未來保證，訊號次數越少，這個百分比越不可靠。" />
                </p>

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
                    <span className="flex items-center text-muted-foreground">
                      中位數報酬
                      <TermTooltip explanation="把所有報酬由小到大排序，最中間那一筆的數字。比「平均報酬」更不容易被少數幾筆暴賺或暴賠的極端值拉偏，比較能代表「一般情況」。" />
                    </span>
                    <span className={`font-medium ${stat.median_return >= 0 ? 'text-primary' : 'text-destructive'}`}>
                      {stat.median_return >= 0 ? '+' : ''}{stat.median_return}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="flex items-center text-muted-foreground">
                      獲利因子
                      <TermTooltip explanation="所有賺錢的次數加起來的獲利，除以所有賠錢的次數加起來的虧損。大於 1 代表整體是賺的，數字越大代表賺的比賠的多越多。" />
                    </span>
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
