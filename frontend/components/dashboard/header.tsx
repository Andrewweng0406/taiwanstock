'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Menu, X } from 'lucide-react';
import { StockSearch } from './stock-search';

const NAV_LINKS = [
  { href: '/', label: '儀表板' },
  { href: '/compare', label: '股票比較' },
  { href: '/backtest', label: '策略回測' },
  { href: '/news', label: '重大訊息' },
  { href: '/watchlist', label: '自選股' },
  { href: '#', label: '設定' },
];

export function DashboardHeader() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
      <header className="border-b border-border bg-card">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold">
              $
            </div>
            <Link href="/" className="text-xl font-bold text-foreground whitespace-nowrap">
              台股量化選股
            </Link>
          </div>

          {/* 手機版塞不下 5 個連結，改成漢堡選單；桌面版維持原本橫向排列。
              之前手機實測發現：5 個連結硬擠在窄螢幕上，每個連結被壓成只有
              一兩個字寬，文字逐字換行，完全不能點，這裡改成響應式解決。 */}
          <nav className="hidden md:flex gap-6">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="text-sm font-medium text-foreground hover:text-primary transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <button
            type="button"
            aria-label={menuOpen ? '關閉選單' : '開啟選單'}
            onClick={() => setMenuOpen((prev) => !prev)}
            className="md:hidden flex h-9 w-9 items-center justify-center rounded-md border border-border text-foreground"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {/* 全站股票搜尋：獨立一整排，不跟 logo/導覽列搶空間，手機、桌面都看得到、
            用得到——之前整個網站沒有地方能直接打代號或名稱查股票，只能從比較頁
            的 8 檔預設按鈕選，或手動在網址列打 /stock/代號，這裡補上。 */}
        <div className="container mx-auto border-t border-border px-4 py-3">
          <StockSearch />
        </div>

        {menuOpen && (
          <nav className="md:hidden border-t border-border bg-card">
            <div className="container mx-auto flex flex-col px-4 py-2">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.label}
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className="py-3 text-base font-medium text-foreground border-b border-border last:border-b-0"
                >
                  {link.label}
                </Link>
              ))}
            </div>
          </nav>
        )}
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
