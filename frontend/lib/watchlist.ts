// 自選股清單：目前整個網站沒有登入系統（見專案規劃：現在自己用、之後才給
// 家人/考慮收費），沒有帳號可以掛資料，先用瀏覽器本機的 localStorage 存，
// 換瀏覽器、換裝置不會同步，但符合現在單機使用的需求，之後真的要做帳號系統
// 時再整個換成後端儲存。

const STORAGE_KEY = 'taiwan-stock-watchlist';

function readRaw(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

function writeRaw(ids: string[]): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  // 讓同一頁面內其他元件（例如 header 上的自選股數量）知道清單變了，
  // storage 事件預設只會通知「其他分頁」，同分頁要自己再發一次。
  window.dispatchEvent(new Event('watchlist-changed'));
}

export function getWatchlist(): string[] {
  return readRaw();
}

export function isInWatchlist(stockId: string): boolean {
  return readRaw().includes(stockId);
}

export function addToWatchlist(stockId: string): void {
  const current = readRaw();
  if (current.includes(stockId)) return;
  writeRaw([...current, stockId]);
}

export function removeFromWatchlist(stockId: string): void {
  const current = readRaw();
  writeRaw(current.filter((id) => id !== stockId));
}

export function toggleWatchlist(stockId: string): boolean {
  const inList = isInWatchlist(stockId);
  if (inList) {
    removeFromWatchlist(stockId);
  } else {
    addToWatchlist(stockId);
  }
  return !inList;
}
