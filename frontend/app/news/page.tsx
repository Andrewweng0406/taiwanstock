'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { DashboardHeader } from '@/components/dashboard/header';
import { TermTooltip } from '@/components/ui/term-tooltip';
import { fetchMaterialNews, type MaterialNewsItem, type NewsSentiment } from '@/lib/api';

const SENTIMENT_STYLES: Record<NewsSentiment, string> = {
  利多: 'bg-primary/10 text-primary border-primary/30',
  利空: 'bg-destructive/10 text-destructive border-destructive/30',
  中性: 'bg-muted text-muted-foreground border-border',
};

function formatAnnouncedTime(item: MaterialNewsItem): string {
  const d = item.announced_date; // ROC 民國年，例如 1150716
  const t = item.announced_time; // 例如 70003 = 07:00:03
  if (!d || d.length < 7) return '—';
  const year = parseInt(d.slice(0, d.length - 4), 10) + 1911;
  const month = d.slice(-4, -2);
  const day = d.slice(-2);
  const timeStr = (t || '').padStart(6, '0');
  const hh = timeStr.slice(0, 2);
  const mm = timeStr.slice(2, 4);
  return `${year}-${month}-${day} ${hh}:${mm}`;
}

function ImportanceDots({ importance }: { importance: number }) {
  return (
    <span className="inline-flex gap-0.5" aria-label={`重要程度 ${importance} / 5`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full ${i < importance ? 'bg-foreground' : 'bg-border'}`}
        />
      ))}
    </span>
  );
}

export default function NewsPage() {
  const [response, setResponse] = useState<Awaited<ReturnType<typeof fetchMaterialNews>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sentimentFilter, setSentimentFilter] = useState<NewsSentiment | 'all'>('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    fetchMaterialNews()
      .then(setResponse)
      .catch((err) => setErrorMessage(err instanceof Error ? err.message : '查詢重大訊息時發生未知錯誤'))
      .finally(() => setLoading(false));
  }, []);

  const items = useMemo(() => {
    const all = response?.data ?? [];
    const keyword = query.trim().toLowerCase();
    return all.filter((item) => {
      if (sentimentFilter !== 'all' && item.sentiment !== sentimentFilter) return false;
      if (keyword && !item.stock_id.includes(keyword) && !item.stock_name.toLowerCase().includes(keyword)) {
        return false;
      }
      return true;
    });
  }, [response, sentimentFilter, query]);

  const counts = useMemo(() => {
    const all = response?.data ?? [];
    return {
      利多: all.filter((i) => i.sentiment === '利多').length,
      利空: all.filter((i) => i.sentiment === '利空').length,
      中性: all.filter((i) => i.sentiment === '中性').length,
    };
  }, [response]);

  return (
    <main className="min-h-screen bg-background">
      <DashboardHeader />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="flex items-center text-2xl font-bold text-foreground">
            重大訊息利多利空看板
            <TermTooltip explanation="資料來源是證交所／櫃買中心官方「重大訊息」開放資料，是上市櫃公司依法必須公告的第一手事實，不是新聞媒體報導。利多/利空/重要程度是 AI 讀過公告內容後的判斷，僅供參考，不是投資建議。" />
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            上市櫃公司官方公告，AI 判讀利多利空與重要程度——不是新聞轉述，是公司依法揭露的第一手事實
          </p>
          {response?.generated_at && (
            <p className="mt-1 text-xs text-amber-600 dark:text-amber-500">
              ⚠️ 資料截至 {response.generated_at} 產生，AI 分類結果僅供參考，不是投資建議，請自行判斷
            </p>
          )}
        </div>

        {errorMessage && (
          <div className="mb-6 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {errorMessage}
          </div>
        )}

        {loading && (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-muted-foreground">
              重大訊息整理中，第一次可能要花一點時間讓 AI 逐則分類，請稍候…
            </p>
          </div>
        )}

        {!loading && !errorMessage && response && (
          <>
            <div className="mb-4 flex flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap gap-2">
                {(['all', '利多', '利空', '中性'] as const).map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSentimentFilter(key)}
                    className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                      sentimentFilter === key
                        ? 'border-foreground bg-foreground text-background'
                        : 'border-border text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {key === 'all' ? `全部 ${response.data.length}` : `${key} ${counts[key]}`}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="篩選股票代號或名稱"
                className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground sm:w-48"
              />
            </div>

            {items.length === 0 && (
              <div className="rounded-lg border border-border bg-card p-12 text-center">
                <p className="text-muted-foreground">沒有符合條件的公告。</p>
              </div>
            )}

            <div className="space-y-3">
              {items.map((item, idx) => (
                <div key={`${item.stock_id}-${idx}`} className="rounded-lg border border-border bg-card p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SENTIMENT_STYLES[item.sentiment]}`}
                      >
                        {item.sentiment}
                      </span>
                      <ImportanceDots importance={item.importance} />
                      <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                        {item.market}
                      </span>
                      <Link href={`/stock/${item.stock_id}`} className="font-semibold text-foreground hover:underline">
                        {item.stock_name}（{item.stock_id}）
                      </Link>
                    </div>
                    <span className="text-xs text-muted-foreground">{formatAnnouncedTime(item)}</span>
                  </div>
                  <p className="mt-2 whitespace-pre-line text-sm text-foreground">{item.subject}</p>
                  {item.reason && <p className="mt-1 text-xs text-muted-foreground">💡 {item.reason}</p>}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </main>
  );
}
