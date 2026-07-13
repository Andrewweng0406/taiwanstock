'use client';

import { useEffect, useRef, useState } from 'react';
import { MessageCircle, X, Send } from 'lucide-react';
import { sendChatMessage } from '@/lib/api';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  displayedContent: string; // 逐字顯示用（打字機效果），user 訊息一開始就等於 content
  source?: 'openai' | 'gemini' | 'fallback';
}

const WELCOME_MESSAGE =
  '您好！我是 AI 選股助理 🙂\n按過上面的「🚀 一鍵掃描全台股」之後，您可以問我「今天有哪些股票入選？」，或是直接跟我說股票代號（例如「2330 怎麼樣？」），我會用簡單的話跟您說明。';

// 打字機效果：每隔一小段時間顯示更多文字，長輩讀起來比一次全部跳出來更好懂、更不突兀。
const TYPEWRITER_CHARS_PER_TICK = 2;
const TYPEWRITER_INTERVAL_MS = 25;

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: WELCOME_MESSAGE, displayedContent: WELCOME_MESSAGE },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const typewriterTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  // 元件卸載時清掉還沒跑完的打字機計時器，避免記憶體洩漏或對已卸載的畫面 setState。
  useEffect(() => {
    return () => {
      if (typewriterTimer.current) clearInterval(typewriterTimer.current);
    };
  }, []);

  const revealWithTypewriter = (fullText: string) => {
    let shown = 0;
    if (typewriterTimer.current) clearInterval(typewriterTimer.current);
    typewriterTimer.current = setInterval(() => {
      shown += TYPEWRITER_CHARS_PER_TICK;
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        if (lastIndex >= 0 && next[lastIndex].role === 'assistant') {
          next[lastIndex] = { ...next[lastIndex], displayedContent: fullText.slice(0, shown) };
        }
        return next;
      });
      if (shown >= fullText.length && typewriterTimer.current) {
        clearInterval(typewriterTimer.current);
        typewriterTimer.current = null;
      }
    }, TYPEWRITER_INTERVAL_MS);
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: 'user', content: trimmed, displayedContent: trimmed }]);
    setInput('');
    setLoading(true);
    setErrorMessage(null);

    try {
      const result = await sendChatMessage(trimmed);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: result.reply, displayedContent: '', source: result.source },
      ]);
      revealWithTypewriter(result.reply);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'AI 助理暫時無法回應，請稍後再試');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {open && (
        <div className="fixed bottom-24 right-4 z-50 flex h-[34rem] w-[23rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl sm:right-6">
          <div className="flex items-center justify-between bg-primary px-4 py-3 text-primary-foreground">
            <span className="text-lg font-bold">🤖 AI 選股助理</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="關閉聊天視窗"
              className="rounded-full p-1.5 hover:bg-primary-foreground/20"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-base leading-relaxed ${
                    msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
                  }`}
                >
                  {msg.displayedContent}
                  {msg.role === 'assistant' && msg.source === 'fallback' && msg.displayedContent === msg.content && (
                    <p className="mt-2 text-xs text-muted-foreground">（目前為規則式回覆，尚未設定 AI 金鑰）</p>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-muted px-4 py-2.5 text-base text-muted-foreground">思考中…</div>
              </div>
            )}
            {errorMessage && (
              <div className="rounded-2xl bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
                {errorMessage}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 border-t border-border p-3">
            <input
              type="text"
              data-testid="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="請輸入您的問題，例如：2330 怎麼樣？"
              disabled={loading}
              className="flex-1 rounded-full border border-input bg-background px-4 py-2.5 text-base text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
            <button
              type="button"
              data-testid="chat-send"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              aria-label="傳送"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-50"
            >
              <Send className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={open ? '關閉 AI 選股助理' : '開啟 AI 選股助理'}
        className="fixed bottom-6 right-4 z-50 flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-xl transition-transform hover:scale-105 sm:right-6"
      >
        {open ? <X className="h-7 w-7" /> : <MessageCircle className="h-7 w-7" />}
      </button>
    </>
  );
}
