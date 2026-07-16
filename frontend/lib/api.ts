// 後端 FastAPI 服務位址。本機開發預設打 localhost:8000（見專案根目錄 main.py）。
// 部署到正式環境時，改用環境變數 NEXT_PUBLIC_API_BASE_URL 覆蓋，不需要改程式碼。
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

// ------------------------------------------------------------------
// 全站股票搜尋（/api/stocks/directory）
// ------------------------------------------------------------------

export interface StockDirectoryEntry {
  stock_id: string;
  stock_name: string;
  close: number;
  change: number | null;
  change_percent: number | null;
}

/**
 * 呼叫後端「全市場股票代號＋名稱對照表」API，給全站搜尋框用。後端當天
 * 第一次呼叫才會真的重抓，之後同一天內都是秒回，所以這裡不用自己另外
 * 做快取，每次進站直接打一次就好。
 */
export async function fetchStockDirectory(): Promise<StockDirectoryEntry[]> {
  const res = await fetch(`${API_BASE_URL}/api/stocks/directory`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `查詢股票清單失敗（HTTP ${res.status}）`);
  }
  const body = await res.json();
  return body.stocks ?? [];
}

export interface ScanResultItem {
  stock_id: string;
  stock_name: string;
  current_price: number;
  volume_multiplier: number;
  revenue_growth_yoy: number;
  institutional_buy_days: number;
  stop_loss_price: number;
}

interface ScanApiResponse {
  success: boolean;
  scan_time?: string;
  trading_date?: string;
  total_count?: number;
  data?: ScanResultItem[];
  from_cache?: boolean;
  message?: string;
  detail?: string;
}

export interface ScanOutcome {
  ok: boolean;
  message?: string;
  scanTime?: string;
  /** 這批資料實際反映的證交所/櫃買中心「最新結算交易日」，不是即時盤中報價 */
  tradingDate?: string;
  fromCache: boolean;
  data: ScanResultItem[];
}

/**
 * 呼叫後端「一鍵掃描全台股」API。
 * - 後端內建當日快取：同一天內預設會直接讀快取秒回（fromCache: true），
 *   不會重新對 TWSE/TPEx 發出上百次請求。傳 force=true 可以略過快取、
 *   強制重新掃描（例如使用者手動按「強制重新掃描」）。
 * - HTTP 423：後端正在計算中，回傳提示訊息而非丟例外，讓畫面顯示「請稍候」。
 * - 其餘非 2xx：視為錯誤，丟出例外由呼叫端顯示錯誤訊息。
 */
export async function scanStocks(force: boolean = false): Promise<ScanOutcome> {
  const url = `${API_BASE_URL}/api/scan${force ? '?force=true' : ''}`;
  const res = await fetch(url, { method: 'POST' });
  const body: ScanApiResponse | null = await res.json().catch(() => null);

  if (res.status === 423) {
    return { ok: false, message: body?.message ?? '系統全自動計算中，請稍候', fromCache: false, data: [] };
  }

  if (!res.ok) {
    throw new Error(body?.detail ?? body?.message ?? `掃描失敗（HTTP ${res.status}）`);
  }

  return {
    ok: true,
    scanTime: body?.scan_time,
    tradingDate: body?.trading_date,
    fromCache: body?.from_cache ?? false,
    data: body?.data ?? [],
  };
}

// ------------------------------------------------------------------
// 回測（/api/backtest）
// ------------------------------------------------------------------

export interface BacktestHoldingStat {
  signal_count: number;
  win_rate: number;
  avg_return: number;
  avg_win: number | null;
  avg_loss: number | null;
  best: number;
  worst: number;
  median_return: number;
  profit_factor: number | null;
}

export interface BacktestSignal {
  stock_id: string;
  stock_name: string;
  signal_date: string;
  entry_date: string;
  entry_price: number;
  return_5: number | null;
  return_10: number | null;
  return_20: number | null;
}

interface BacktestApiResponse {
  success: boolean;
  run_time?: string;
  lookback_days?: number;
  holding_periods?: number[];
  watchlist_size?: number;
  summary?: Record<string, BacktestHoldingStat | null>;
  signals?: BacktestSignal[];
  message?: string;
  detail?: string;
}

export interface BacktestOutcome {
  ok: boolean;
  message?: string;
  runTime?: string;
  lookbackDays?: number;
  holdingPeriods?: number[];
  watchlistSize?: number;
  summary: Record<string, BacktestHoldingStat | null>;
  signals: BacktestSignal[];
}

/**
 * 呼叫後端「執行回測」API，預設驗證選股規則過去五年的勝率。
 * 跟 scanStocks() 共用同一把後端鎖（heavy_task_lock），兩者不會同時執行，
 * 一次大約需要 2-3 分鐘（要對觀察清單每一檔股票個別打 FinMind API）。
 */
export async function runBacktest(): Promise<BacktestOutcome> {
  const res = await fetch(`${API_BASE_URL}/api/backtest`, { method: 'POST' });
  const body: BacktestApiResponse | null = await res.json().catch(() => null);

  if (res.status === 423) {
    return { ok: false, message: body?.message ?? '系統全自動計算中，請稍候', summary: {}, signals: [] };
  }

  if (!res.ok) {
    throw new Error(body?.detail ?? body?.message ?? `回測失敗（HTTP ${res.status}）`);
  }

  return {
    ok: true,
    runTime: body?.run_time,
    lookbackDays: body?.lookback_days,
    holdingPeriods: body?.holding_periods,
    watchlistSize: body?.watchlist_size,
    summary: body?.summary ?? {},
    signals: body?.signals ?? [],
  };
}

// ------------------------------------------------------------------
// 個股詳情（/api/stock/{stock_id}）
// ------------------------------------------------------------------

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  ma5: number | null;
  ma20: number | null;
  ma50: number | null;
}

export interface TechnicalIndicators {
  rsi: number | null;
  macd: number | null;
  signal: number | null;
  histogram: number | null;
  ma20: number | null;
  ma50: number | null;
  ma200: number | null;
}

export interface RevenueTrendPoint {
  month: string;
  revenue: number;
  yoy: number | null;
}

export interface InstitutionalDay {
  date: string;
  buy_lots: number;
  sell_lots: number;
  net_buy_lots: number;
}

export interface StockDetail {
  stock_id: string;
  stock_name: string;
  industry: string | null;
  current_price: number;
  /** current_price 實際對應的交易日（收盤價），不是即時報價的時間戳 */
  price_date: string;
  change: number;
  change_percent: number;
  volume: number;
  volume_avg: number | null;
  pe: number | null;
  pb: number | null;
  dividend_yield: number | null;
  capital: number | null;
  market_cap: number | null;
  price_history: PricePoint[];
  technical_indicators: TechnicalIndicators;
  revenue_trend: RevenueTrendPoint[];
  institutional_recent: InstitutionalDay[];
}

/**
 * 呼叫後端「查詢單一股票詳情」API，股票比較／個股詳情頁用。
 * 資料來源是 FinMind（單股查詢，跟 /api/scan 的全市場資料源不同，見 main.py
 * 第 9 節說明），一次查詢通常幾秒內完成，不用排隊等 heavy_task_lock。
 * - HTTP 404：查無此股票代號，回傳 null 讓呼叫端顯示「找不到」。
 * - 其餘非 2xx：視為錯誤，丟出例外由呼叫端顯示錯誤訊息。
 */
export async function fetchStockDetail(stockId: string): Promise<StockDetail | null> {
  const res = await fetch(`${API_BASE_URL}/api/stock/${encodeURIComponent(stockId)}`);

  if (res.status === 404) {
    return null;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `查詢股票資料失敗（HTTP ${res.status}）`);
  }

  return res.json();
}

// ------------------------------------------------------------------
// 大盤情緒（/api/market-sentiment）
// ------------------------------------------------------------------

export interface FuturesQuote {
  contract: string;
  expiry_month: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  change: number | null;
  change_percent: number | null;
  volume: number | null;
  settlement_price: number | null;
  open_interest: number | null;
  date: string;
}

export interface InstitutionalFuturesPosition {
  long_position: number | null;
  short_position: number | null;
  net_position: number | null;
  net_position_amount: number | null;
}

export interface MarketSentiment {
  trading_date: string;
  futures: FuturesQuote;
  /** 三大法人未平倉報表的資料日期，可能跟 trading_date 不同天（兩份報表發布時間不同步） */
  positions_date: string | null;
  dealer_position: InstitutionalFuturesPosition | null;
  trust_position: InstitutionalFuturesPosition | null;
  foreign_position: InstitutionalFuturesPosition | null;
}

/**
 * 呼叫後端「大盤情緒」API：台指期近月行情 + 三大法人期貨未平倉（自營商/投信/外資）。
 * 跟現貨資料一樣是收盤後才有的資料，不是即時盤中報價，回應裡的 trading_date
 * 就是實際反映哪一天的資料，前端要照樣清楚標示，不能讓人誤會成即時行情。
 * - HTTP 404：查不到資料（例如 TAIFEX 服務異常、連續假期），回傳 null 讓
 *   呼叫端把整張卡片藏起來，不顯示殘缺資料。
 */
export async function fetchMarketSentiment(): Promise<MarketSentiment | null> {
  const res = await fetch(`${API_BASE_URL}/api/market-sentiment`);

  if (res.status === 404) {
    return null;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `查詢大盤情緒失敗（HTTP ${res.status}）`);
  }

  return res.json();
}

// ------------------------------------------------------------------
// AI 選股助理（/api/chat）
// ------------------------------------------------------------------

export interface ChatResponse {
  reply: string;
  source: 'openai' | 'gemini' | 'fallback';
}

interface ChatApiResponse {
  success: boolean;
  reply?: string;
  source?: 'openai' | 'gemini' | 'fallback';
  detail?: string;
}

/**
 * 呼叫後端「AI 選股助理」API。後端會把最新一次 /api/scan 的快取結果當
 * 背景資料，讓 AI 根據真實資料回答問題。source 為 "fallback" 時代表後端
 * 還沒設定 OPENAI_API_KEY / GEMINI_API_KEY，回覆是規則式模板，不是真正的 AI。
 */
export async function sendChatMessage(userMessage: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_message: userMessage }),
  });
  const body: ChatApiResponse | null = await res.json().catch(() => null);

  if (!res.ok) {
    throw new Error(body?.detail ?? `AI 助理暫時無法回應（HTTP ${res.status}）`);
  }

  return { reply: body?.reply ?? '（沒有收到回覆）', source: body?.source ?? 'fallback' };
}
