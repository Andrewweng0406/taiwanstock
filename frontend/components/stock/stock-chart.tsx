'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface StockChartProps {
  data: Array<{ date: string; price: number }>;
}

export function StockChart({ data }: StockChartProps) {
  const minPrice = Math.min(...data.map((d) => d.price));
  const maxPrice = Math.max(...data.map((d) => d.price));
  const padding = (maxPrice - minPrice) * 0.1;

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' });
  };

  const chartData = data.map((d) => ({
    ...d,
    displayDate: formatDate(d.date),
  }));

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis
          dataKey="displayDate"
          stroke="var(--color-muted-foreground)"
          style={{ fontSize: '12px' }}
        />
        <YAxis
          stroke="var(--color-muted-foreground)"
          domain={[minPrice - padding, maxPrice + padding]}
          style={{ fontSize: '12px' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--color-card)',
            border: `1px solid var(--color-border)`,
            borderRadius: '8px',
            color: 'var(--color-foreground)',
          }}
          formatter={(value) => [`NT$${Number(value).toFixed(2)}`, '股價']}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke="var(--color-primary)"
          dot={false}
          strokeWidth={2}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
