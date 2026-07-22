'use client';

import { useEffect, useState } from 'react';
import { fetchSchedulerHealth, type SchedulerJobHealth } from '@/lib/api';

const JOB_LABELS: Record<string, string> = {
  post_market_scan: '收盤後自動掃描（14:30）',
  post_market_paper_trade: '紙上交易記錄（14:45）',
  post_market_material_news: '重大訊息分類（14:50）',
};

/**
 * 內部用的排程健康檢查頁面，故意不放進 DashboardHeader 的導覽列——這是
 * 給自己偶爾檢查用的，不是給家人看的功能，直接打網址 /status 進來即可。
 */
export default function StatusPage() {
  const [jobs, setJobs] = useState<SchedulerJobHealth[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchSchedulerHealth()
      .then(setJobs)
      .catch((err) => setErrorMessage(err instanceof Error ? err.message : '查詢失敗'));
  }, []);

  return (
    <main className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-1 text-xl font-bold text-foreground">背景排程健康檢查</h1>
        <p className="mb-6 text-sm text-muted-foreground">
          內部檢查頁，不是主要功能。伺服器重開機後，還沒到排程時間的項目會顯示「尚無紀錄」，這是正常的，不是錯誤。
        </p>

        {errorMessage && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {errorMessage}
          </div>
        )}

        {!jobs && !errorMessage && <p className="text-sm text-muted-foreground">載入中…</p>}

        {jobs && (
          <div className="space-y-3">
            {jobs.map((job) => (
              <div key={job.job_id} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-foreground">{JOB_LABELS[job.job_id] ?? job.job_id}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      job.status === 'success'
                        ? 'bg-primary/10 text-primary'
                        : job.status === 'failed'
                          ? 'bg-destructive/10 text-destructive'
                          : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {job.status === 'success' ? '成功' : job.status === 'failed' ? '失敗' : job.status}
                  </span>
                </div>
                <dl className="mt-2 space-y-1 text-sm text-muted-foreground">
                  <div className="flex justify-between">
                    <dt>最近執行時間</dt>
                    <dd>{job.last_run_at ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>下次預定執行</dt>
                    <dd>{job.next_run_time ?? '—'}</dd>
                  </div>
                  {job.detail && (
                    <div className="flex justify-between gap-4">
                      <dt className="shrink-0">結果</dt>
                      <dd className="text-right">{job.detail}</dd>
                    </div>
                  )}
                </dl>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
