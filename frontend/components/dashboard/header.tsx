import Link from 'next/link';

export function DashboardHeader() {
  return (
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
  );
}
