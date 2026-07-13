'use client';

import Link from 'next/link';
import { DashboardHeader } from '@/components/dashboard/header';
import { PriceComparator } from '@/components/stock/price-comparator';
import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';

export default function ComparePage() {
  return (
    <div className="min-h-screen bg-background">
      <DashboardHeader />
      <div className="container mx-auto px-4 py-8">
        <Link href="/">
          <Button variant="outline" className="mb-6">
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回儀表板
          </Button>
        </Link>

        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">股票比較</h1>
          <p className="text-muted-foreground">最多可選擇 3 檔股票，比較關鍵指標與表現</p>
        </div>

        <PriceComparator />
      </div>
    </div>
  );
}
