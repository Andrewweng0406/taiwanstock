'use client';

import { useState } from 'react';
import { DashboardHeader } from '@/components/dashboard/header';
import { StockScreener } from '@/components/dashboard/stock-screener';
import { KeyMetrics } from '@/components/dashboard/key-metrics';
import { ChatWidget } from '@/components/chat/chat-widget';
import { Button } from '@/components/ui/button';
import { scanStocks, type ScanResultItem } from '@/lib/api';

export default function Page() {
  const [loading, setLoading] = useState(false);
  const [hasScanned, setHasScanned] = useState(false);
  const [results, setResults] = useState<ScanResultItem[]>([]);
  const [scanTime, setScanTime] = useState<string | null>(null);
  const [tradingDate, setTradingDate] = useState<string | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleScan = async (force: boolean = false) => {
    if (loading) return; // 前端也擋一次，避免同一顆按鈕被連點
    setLoading(true);
    setErrorMessage(null);
    try {
      const outcome = await scanStocks(force);
      if (!outcome.ok) {
        setErrorMessage(outcome.message ?? '系統全自動計算中，請稍候');
        return;
      }
      setResults(outcome.data);
      setScanTime(outcome.scanTime ?? null);
      setTradingDate(outcome.tradingDate ?? null);
      setFromCache(outcome.fromCache);
      setHasScanned(true);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '掃描過程發生未知錯誤，請稍後再試');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-background">
      <DashboardHeader />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8 flex flex-col items-start justify-between gap-4 rounded-lg border border-border bg-card p-6 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-bold text-foreground">台股三大生態選股</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              技術面（5MA / 20MA + 爆量）× 籌碼面（投信連續買超）× 基本面（營收年增率 + 股本）
            </p>
            {scanTime && (
              <p className="mt-1 text-xs text-muted-foreground">
                上次更新時間：{scanTime}
                {fromCache ? '（快取資料）' : '（剛剛更新）'}
                {fromCache && (
                  <button
                    type="button"
                    onClick={() => handleScan(true)}
                    disabled={loading}
                    className="ml-2 text-primary underline-offset-2 hover:underline disabled:opacity-50"
                  >
                    強制重新掃描
                  </button>
                )}
              </p>
            )}
            {tradingDate && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-500">
                ⚠️ 資料截至 {tradingDate} 收盤結算，為證交所/櫃買中心收盤後公布資料，非即時盤中報價
              </p>
            )}
          </div>
          <Button onClick={() => handleScan(false)} disabled={loading} size="lg" className="whitespace-nowrap px-6">
            {loading ? '掃描中…' : '🚀 一鍵掃描全台股'}
          </Button>
        </div>

        {errorMessage && (
          <div className="mb-8 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {errorMessage}
          </div>
        )}

        <KeyMetrics results={results} />
        <div className="mt-8">
          <StockScreener results={results} loading={loading} hasScanned={hasScanned} />
        </div>
      </div>

      <ChatWidget />
    </main>
  );
}
