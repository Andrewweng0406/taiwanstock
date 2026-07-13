import type { RevenueTrendPoint } from '@/lib/api';

interface RevenueTrendProps {
  data: RevenueTrendPoint[];
}

export function RevenueTrend({ data }: RevenueTrendProps) {
  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="mb-2 text-lg font-semibold text-foreground">營收趨勢</h2>
        <p className="text-sm text-muted-foreground">目前查無這檔股票的月營收資料。</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-4 text-lg font-semibold text-foreground">營收趨勢（近 {data.length} 個月）</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left font-semibold text-foreground">月份</th>
              <th className="px-3 py-2 text-left font-semibold text-foreground">營收（億）</th>
              <th className="px-3 py-2 text-left font-semibold text-foreground">年增率</th>
            </tr>
          </thead>
          <tbody>
            {data.map((point) => (
              <tr key={point.month} className="border-b border-border hover:bg-muted/30">
                <td className="px-3 py-2 text-foreground">{point.month}</td>
                <td className="px-3 py-2 text-foreground">{(point.revenue / 100_000_000).toFixed(1)}</td>
                <td className="px-3 py-2">
                  {point.yoy === null ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <span className={point.yoy >= 0 ? 'font-medium text-primary' : 'font-medium text-destructive'}>
                      {point.yoy >= 0 ? '+' : ''}
                      {point.yoy}%
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
