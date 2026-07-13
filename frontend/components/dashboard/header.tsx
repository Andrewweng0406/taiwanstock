import Link from 'next/link';

export function DashboardHeader() {
  return (
    <>
      <header className="border-b border-border bg-card">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold">
              $
            </div>
            <Link href="/" className="text-xl font-bold text-foreground">
              台股量化選股
            </Link>
          </div>
          <nav className="flex gap-6">
            <Link
              href="/"
              className="text-sm font-medium text-foreground hover:text-primary transition-colors"
            >
              儀表板
            </Link>
            <Link
              href="/compare"
              className="text-sm font-medium text-foreground hover:text-primary transition-colors"
            >
              股票比較
            </Link>
            <Link
              href="/backtest"
              className="text-sm font-medium text-foreground hover:text-primary transition-colors"
            >
              策略回測
            </Link>
            <Link
              href="#"
              className="text-sm font-medium text-foreground hover:text-primary transition-colors"
            >
              自選股
            </Link>
            <Link
              href="#"
              className="text-sm font-medium text-foreground hover:text-primary transition-colors"
            >
              設定
            </Link>
          </nav>
        </div>
      </header>
      {/* 全站風險揭露：所有頁面都經過 DashboardHeader，寫在這裡一次涵蓋全站，
          不用每個頁面各自加一次、以後也不會漏掉新頁面。用白話、溫和的語氣，
          是寫給不熟悉這個工具限制的家人看的，不是寫給工程師看的技術性免責聲明。 */}
      <div className="border-b border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40">
        <div className="container mx-auto px-4 py-2 text-center text-xs leading-relaxed text-amber-800 dark:text-amber-300">
          💡 溫馨提醒：這個網站只是幫你整理股市資料、統計歷史規則的參考工具，<strong>不是投資建議</strong>，
          也不是叫你現在買什麼股票。過去統計起來準，不代表以後一定準，投資一定有賺有賠，
          請自己判斷、量力而為，不要看到網站顯示什麼就衝動下單。
        </div>
      </div>
    </>
  );
}
