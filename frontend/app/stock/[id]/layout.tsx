import { DashboardHeader } from '@/components/dashboard/header';

export default function StockDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      <DashboardHeader />
      {children}
    </div>
  );
}
