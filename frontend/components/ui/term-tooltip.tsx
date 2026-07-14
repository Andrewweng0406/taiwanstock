'use client';

import { useState } from 'react';
import { HelpCircle } from 'lucide-react';

interface TermTooltipProps {
  explanation: string;
}

/**
 * 專有名詞旁邊的小「?」按鈕，點一下彈出白話解釋，再點一次收起。
 * 用 click 而不是 hover，是因為手機沒有 hover，家人用手機看的時候
 * 才點得到；onBlur 讓點別的地方時自動收起，不用額外處理「點外面關閉」。
 */
export function TermTooltip({ explanation }: TermTooltipProps) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-label="名詞說明"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((prev) => !prev);
        }}
        onBlur={() => setOpen(false)}
        className="ml-1 inline-flex h-4 w-4 shrink-0 items-center justify-center align-middle text-muted-foreground hover:text-primary"
      >
        <HelpCircle className="h-3.5 w-3.5" />
      </button>
      {open && (
        <span
          className="absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded-md border border-border bg-popover p-2.5 text-left text-xs font-normal normal-case leading-relaxed text-popover-foreground shadow-lg"
        >
          {explanation}
        </span>
      )}
    </span>
  );
}
