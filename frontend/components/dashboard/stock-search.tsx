'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';
import { fetchStockDirectory, type StockDirectoryEntry } from '@/lib/api';

const MAX_RESULTS = 8;

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

  useEffect(() => {
    fetchStockDirectory()
      .then(setDirectory)
      .catch(() => {
        // 搜尋清單抓不到就靜靜失敗，不影響網站其他功能；使用者頂多是搜尋框沒結果
      });
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
        <ul className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-border bg-popover shadow-lg">
          {matches.map((item) => (
            <li key={item.stock_id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()} // 避免先觸發 input 的 onBlur 把清單收起來
                onClick={() => goToStock(item.stock_id)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm text-popover-foreground hover:bg-muted"
              >
                <span className="font-medium">{item.stock_name}</span>
                <span className="text-muted-foreground">{item.stock_id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && query.trim() && matches.length === 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover px-3 py-2 text-sm text-muted-foreground shadow-lg">
          找不到符合的股票
        </div>
      )}
    </div>
  );
}
