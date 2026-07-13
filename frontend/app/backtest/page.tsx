'use client';

import { useState } from 'react';
import { DashboardHeader } from '@/components/dashboard/header';
import { BacktestSummary } from '@/components/backtest/backtest-summary';
import { SignalTable } from '@/components/backtest/signal-table';
import { Button } from '@/components/ui/button';
import { runBacktest, type BacktestHoldingStat, type BacktestSignal } from '@/lib/api';

export default function BacktestPage() {
  const [loading, setLoading] = useState(false);
  const [hasRun, setHasRun] = useState(false);
  const [summary, setSummary] = useState<Record<string, BacktestHoldingStat | null>>({});
  const [signals, setSignals] = useState<BacktestSignal[]>([]);
  const [holdingPeriods, setHoldingPeriods] = useState<number[]>([5, 10, 20]);
  const [runTime, setRunTime] = useState<string | null>(null);
  const [lookbackDays, setLookbackDays] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleRun = async () => {
    if (loading) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const outcome = await runBacktest();
      if (!outcome.ok) {
        setErrorMessage(outcome.message ?? '系統全自動計算中，請稍候');
        return;
      }
      setSummary(outcome.summary);
      setSignals(outcome.signals);
      if (outcome.holdingPeriods) setHoldingPeriods(outcome.holdingPeriods);
      setRunTime(outcome.runTime ?? null);
      setLookbackDays(outcome.lookbackDays ?? null);
      setHasRun(true);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '回測過程發生未知錯誤，請稍後再試');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-background">
      <DashboardHeader />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6 flex flex-col items-start justify-between gap-4 rounded-lg border border-border bg-card p-6 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-bold text-foreground">策略回測</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              驗證「三大生態選股」規則過去 {lookbackDays ?? 1825} 天的勝率，而不是只看今天符不符合條件
            </p>
            {runTime && <p className="mt-1 text-xs text-muted-foreground">上次執行時間：{runTime}</p>}
          </div>
          <Button onClick={handleRun} disabled={loading} size="lg" className="whitespace-nowrap px-6">
            {loading ? '回測執行中…' : '🔬 執行回測'}
          </Button>
        </div>

        <div className="mb-8 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">看數字之前，先看這幾點限制：</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>預設回測五年，但樣本仍只限於後端觀察清單；訊號數少時不可只看勝率</li>
            <li>訊號收盤後才成立，以次一交易日開盤進場；已計入買賣手續費、單邊 0.1% 滑價與賣出證交稅</li>
            <li>同一檔連續數日符合只計第一天，避免同一段漲勢被當成多筆獨立交易</li>
            <li>沒有處理下市、減資、除權息造成的價格跳動</li>
            <li>
              已套用「股本 &lt; 40 億」（用財報公佈延遲後的股本，避免用到未來資訊），
              跟即時掃描是同一套四條件；但後端觀察清單以大型權值股為主，符合股本
              門檻的檔數本來就少，訊號數可能明顯偏低
            </li>
          </ul>
        </div>

        {errorMessage && (
          <div className="mb-8 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {errorMessage}
          </div>
        )}

        {loading && (
          <div className="mb-8 rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-muted-foreground">
              回測執行中，要對觀察清單每一檔股票個別向 FinMind 要一年份資料，通常需要 2-3 分鐘，請稍候…
            </p>
          </div>
        )}

        {!loading && hasRun && (
          <>
            <h2 className="mb-4 text-2xl font-bold text-foreground">勝率統計</h2>
            <BacktestSummary summary={summary} holdingPeriods={holdingPeriods} />

            <h2 className="mb-4 mt-8 text-2xl font-bold text-foreground">
              訊號清單（最新 {signals.length} 筆）
            </h2>
            <SignalTable signals={signals} />
          </>
        )}

        {!loading && !hasRun && !errorMessage && (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-muted-foreground">按下上方「🔬 執行回測」開始驗證勝率。</p>
          </div>
        )}
      </div>
    </main>
  );
}
