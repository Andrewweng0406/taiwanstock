'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';
import { fetchStockDirectory, type StockDirectoryEntry } from '@/lib/api';

const MAX_RESULTS = 10;

function formatChange(item: StockDirectoryEntry): { text: string; className: string } {
  if (item.change === null || item.change_percent === null) {
    return { text: '—', className: 'text-muted-foreground' };
  }
  const sign = item.change >= 0 ? '+' : '';
  return {
    text: `${sign}${item.change.toFixed(2)}（${sign}${item.change_percent.toFixed(2)}%）`,
    className: item.change >= 0 ? 'text-primary' : 'text-destructive',
  };
}

/**
 * 全站搜尋框：輸入股票代號或名稱，點選（或按 Enter 選到唯一/完全符合的代號）
 * 直接跳到該股票的詳情頁。放在 DashboardHeader 裡，所有頁面都看得到、用得到，
 * 不用像之前一樣只能從比較頁的 8 檔預設按鈕選，或是手動在網址列打代號。
 */
export function StockSearch() {
  const router = useRouter();
  const [directory, setDirectory] = useState<StockDirectoryEntry[]>([]);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  // 之前這裡失敗是靜靜吞掉，使用者只會看到「找不到符合的股票」，跟真的
  // 沒有符合結果長得一模一樣，完全看不出來是搜尋功能本身壞了——實測真的
  // 遇過一次（後端資料源暫時不穩），完全沒有線索可以判斷是不是網站故障。
  // 現在區分「清單載入失敗」跟「載入成功但沒有符合結果」這兩種狀態，
  // 分別顯示不同訊息，並提供重試按鈕。
  const [loadFailed, setLoadFailed] = useState(false);

  const loadDirectory = () => {
    setLoadFailed(false);
    fetchStockDirectory()
      .then(setDirectory)
      .catch(() => setLoadFailed(true));
  };

  useEffect(() => {
    loadDirectory();
  }, []);

  const matches = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return [];
    return directory
      .filter(
        (item) => item.stock_id.toLowerCase().includes(keyword) || item.stock_name.toLowerCase().includes(keyword)
      )
      .slice(0, MAX_RESULTS);
  }, [directory, query]);

  const goToStock = (stockId: string) => {
    setQuery('');
    setOpen(false);
    router.push(`/stock/${stockId}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    const keyword = query.trim();
    if (!keyword) return;
    // 完全打對代號就直接跳轉；不然選清單裡的第一筆符合結果
    const exact = directory.find((item) => item.stock_id === keyword);
    if (exact) {
      goToStock(exact.stock_id);
    } else if (matches.length > 0) {
      goToStock(matches[0].stock_id);
    }
  };

  return (
    <div className="relative w-full max-w-sm">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder="搜尋股票代號或名稱，例如：2330、台積電"
          data-testid="global-stock-search"
          className="h-9 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      {open && matches.length > 0 && (
        <ul className="absolute z-50 mt-1 max-h-96 w-full overflow-y-auto rounded-md border border-border bg-popover shadow-lg">
          {matches.map((item) => {
            const change = formatChange(item);
            return (
              <li key={item.stock_id}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()} // 避免先觸發 input 的 onBlur 把清單收起來
                  onClick={() => goToStock(item.stock_id)}
                  className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm text-popover-foreground hover:bg-muted"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{item.stock_name}</span>
                    <span className="block text-xs text-muted-foreground">{item.stock_id}</span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block font-medium">{item.close.toFixed(2)}</span>
                    <span className={`block text-xs ${change.className}`}>{change.text}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {open && query.trim() && matches.length === 0 && loadFailed && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-lg">
          <p className="text-destructive">搜尋功能暫時無法使用，股票清單載入失敗</p>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={loadDirectory}
            className="mt-1 text-primary underline-offset-2 hover:underline"
          >
            重試
          </button>
        </div>
      )}

      {open && query.trim() && matches.length === 0 && !loadFailed && directory.length > 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover px-3 py-2 text-sm text-muted-foreground shadow-lg">
          找不到符合的股票
        </div>
      )}

      {open && query.trim() && matches.length === 0 && !loadFailed && directory.length === 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover px-3 py-2 text-sm text-muted-foreground shadow-lg">
          股票清單載入中…
        </div>
      )}
    </div>
  );
}
