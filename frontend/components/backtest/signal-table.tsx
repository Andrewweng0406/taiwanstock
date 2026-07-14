import type { BacktestSignal } from '@/lib/api';

interface SignalTableProps {
  signals: BacktestSignal[];
}

function ReturnCell({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-muted-foreground">尚未滿期</span>;
  }
  const color = value >= 0 ? 'text-primary' : 'text-destructive';
  return (
    <span className={`font-medium ${color}`}>
      {value >= 0 ? '+' : ''}
      {value}%
    </span>
  );
}

export function SignalTable({ signals }: SignalTableProps) {
  if (signals.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-12 text-center">
        <p className="text-muted-foreground">回測窗口內沒有出現任何符合三大條件的訊號。</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[800px]">
        <thead>
          <tr className="border-b border-border bg-card">
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票代號</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">股票名稱</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">訊號日期</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">次日進場</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">進場價</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">5日報酬</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">10日報酬</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">20日報酬</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => (
            <tr
              key={`${s.stock_id}-${s.signal_date}-${i}`}
              className="border-b border-border hover:bg-muted/30 transition-colors"
            >
              <td className="px-4 py-3 font-semibold text-foreground">{s.stock_id}</td>
              <td className="px-4 py-3 text-foreground">{s.stock_name}</td>
              <td className="px-4 py-3 text-foreground">{s.signal_date}</td>
              <td className="px-4 py-3 text-foreground">{s.entry_date}</td>
              <td className="px-4 py-3 text-foreground">NT${s.entry_price.toFixed(2)}</td>
              <td className="px-4 py-3">
                <ReturnCell value={s.return_5} />
              </td>
              <td className="px-4 py-3">
                <ReturnCell value={s.return_10} />
              </td>
              <td className="px-4 py-3">
                <ReturnCell value={s.return_20} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
