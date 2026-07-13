'use client';

import type { ScanResultItem } from '@/lib/api';

interface KeyMetricsProps {
  results: ScanResultItem[];
}

export function KeyMetrics({ results }: KeyMetricsProps) {
  const count = results.length;
  const avgVolumeMultiplier = count
    ? (results.reduce((sum, s) => sum + s.volume_multiplier, 0) / count).toFixed(2)
    : '—';
  const avgRevenueGrowth = count
    ? (results.reduce((sum, s) => sum + s.revenue_growth_yoy, 0) / count).toFixed(1)
    : '—';
  const topPick = count
    ? results.reduce((max, s) => (s.volume_multiplier > max.volume_multiplier ? s : max))
    : null;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
      <div className="rounded-lg border border-border bg-card p-6">
        <p className="text-sm font-medium text-muted-foreground">符合條件檔數</p>
        <p className="mt-2 text-2xl font-bold text-foreground">{count} 檔</p>
      </div>
      <div className="rounded-lg border border-border bg-card p-6">
        <p className="text-sm font-medium text-muted-foreground">平均量能倍數</p>
        <p className="mt-2 text-2xl font-bold text-foreground">
          {avgVolumeMultiplier}
          {count ? 'x' : ''}
        </p>
      </div>
      <div className="rounded-lg border border-border bg-card p-6">
        <p className="text-sm font-medium text-muted-foreground">平均營收年增率</p>
        <p className="mt-2 text-2xl font-bold text-foreground">
          {avgRevenueGrowth}
          {count ? '%' : ''}
        </p>
      </div>
      <div className="rounded-lg border border-border bg-card p-6">
        <p className="text-sm font-medium text-muted-foreground">量能最強</p>
        <p className="mt-2 text-lg font-bold text-foreground">{topPick ? topPick.stock_name : '—'}</p>
        {topPick && (
          <p className="text-sm font-medium text-primary">{topPick.volume_multiplier.toFixed(2)}x</p>
        )}
      </div>
    </div>
  );
}
