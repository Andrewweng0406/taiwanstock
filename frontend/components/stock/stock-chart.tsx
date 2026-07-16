'use client';

import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { PricePoint } from '@/lib/api';

interface StockChartProps {
  data: PricePoint[];
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr);
  return date.toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' });
}

interface CandlestickProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: PricePoint;
}

// Recharts 沒有內建 K 線圖元件，這裡用 Bar 的 dataKey 回傳 [low, high]，讓
// Recharts 算出每根蠟燭在圖上對應的 y 座標範圍（y 到 y+height 就是 high 到
// low 的像素區間），再用這個線性關係自己反推 open/close 的像素位置，畫出
// 上下影線＋實體柱。顏色跟著網站其他地方的漲跌配色（漲=primary、跌=
// destructive），不是台股傳統的紅漲綠跌，是為了跟網站其他頁面一致，避免
// 同一個使用者在不同頁面看到相反的顏色意義。
function Candlestick({ x, y, width, height, payload }: CandlestickProps) {
  if (x === undefined || y === undefined || width === undefined || height === undefined || !payload) return null;
  const { open, close, high, low } = payload;
  if ([open, close, high, low].some((v) => v === null || v === undefined)) return null;

  const isUp = close >= open;
  const color = isUp ? 'var(--color-primary)' : 'var(--color-destructive)';
  const priceRange = high - low || 1;
  const scale = height / priceRange;
  const openY = y + (high - open) * scale;
  const closeY = y + (high - close) * scale;
  const bodyTop = Math.min(openY, closeY);
  const bodyHeight = Math.max(Math.abs(closeY - openY), 1);
  const centerX = x + width / 2;

  return (
    <g>
      <line x1={centerX} x2={centerX} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={x} y={bodyTop} width={width} height={bodyHeight} fill={color} />
    </g>
  );
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: PricePoint }> }) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-card p-3 text-xs shadow-lg">
      <p className="mb-1 font-semibold text-foreground">{point.date}</p>
      <p className="text-muted-foreground">
        開 {point.open.toFixed(2)} ／ 高 {point.high.toFixed(2)} ／ 低 {point.low.toFixed(2)} ／ 收{' '}
        {point.close.toFixed(2)}
      </p>
      {point.ma5 !== null && <p style={{ color: '#f59e0b' }}>MA5：{point.ma5.toFixed(2)}</p>}
      {point.ma20 !== null && <p style={{ color: '#3b82f6' }}>MA20：{point.ma20.toFixed(2)}</p>}
      {point.ma50 !== null && <p style={{ color: '#a855f7' }}>MA50：{point.ma50.toFixed(2)}</p>}
    </div>
  );
}

export function StockChart({ data }: StockChartProps) {
  const lows = data.map((d) => d.low);
  const highs = data.map((d) => d.high);
  const minPrice = Math.min(...lows);
  const maxPrice = Math.max(...highs);
  const padding = (maxPrice - minPrice) * 0.1 || 1;

  const chartData = data.map((d) => ({
    ...d,
    displayDate: formatDate(d.date),
    range: [d.low, d.high] as [number, number],
  }));

  // 資料點一多，X 軸標籤會擠成一團看不清楚，這裡抓大概只顯示 6-8 個標籤。
  const tickInterval = Math.max(Math.floor(chartData.length / 7), 0);

  return (
    <ResponsiveContainer width="100%" height={400}>
      <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis
          dataKey="displayDate"
          stroke="var(--color-muted-foreground)"
          style={{ fontSize: '12px' }}
          interval={tickInterval}
        />
        <YAxis
          stroke="var(--color-muted-foreground)"
          domain={[minPrice - padding, maxPrice + padding]}
          style={{ fontSize: '12px' }}
          width={55}
        />
        <Tooltip content={<ChartTooltip />} />
        <Legend wrapperStyle={{ fontSize: '12px' }} />
        <Bar dataKey="range" name="K線" shape={Candlestick} isAnimationActive={false} />
        <Line type="monotone" dataKey="ma5" name="MA5" stroke="#f59e0b" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />
        <Line type="monotone" dataKey="ma20" name="MA20" stroke="#3b82f6" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />
        <Line type="monotone" dataKey="ma50" name="MA50" stroke="#a855f7" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
