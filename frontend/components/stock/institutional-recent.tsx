import type { InstitutionalDay } from '@/lib/api';

interface InstitutionalRecentProps {
  data: InstitutionalDay[];
}

export function InstitutionalRecent({ data }: InstitutionalRecentProps) {
  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="mb-2 text-lg font-semibold text-foreground">投信買賣超明細</h2>
        <p className="text-sm text-muted-foreground">目前查無這檔股票的投信買賣超資料。</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-4 text-lg font-semibold text-foreground">投信買賣超明細（近 {data.length} 個交易日）</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left font-semibold text-foreground">日期</th>
              <th className="px-3 py-2 text-left font-semibold text-foreground">買進（張）</th>
              <th className="px-3 py-2 text-left font-semibold text-foreground">賣出（張）</th>
              <th className="px-3 py-2 text-left font-semibold text-foreground">買賣超（張）</th>
            </tr>
          </thead>
          <tbody>
            {[...data].reverse().map((day) => (
              <tr key={day.date} className="border-b border-border hover:bg-muted/30">
                <td className="px-3 py-2 text-foreground">{day.date}</td>
                <td className="px-3 py-2 text-foreground">{day.buy_lots.toLocaleString()}</td>
                <td className="px-3 py-2 text-foreground">{day.sell_lots.toLocaleString()}</td>
                <td className="px-3 py-2">
                  <span
                    className={day.net_buy_lots >= 0 ? 'font-medium text-primary' : 'font-medium text-destructive'}
                  >
                    {day.net_buy_lots >= 0 ? '+' : ''}
                    {day.net_buy_lots.toLocaleString()}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
