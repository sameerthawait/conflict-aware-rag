"use client";

import React, { useRef, useState, useEffect, useCallback } from "react";
import { ArrowUp, Loader2, AlertCircle } from "lucide-react";
import clsx from "clsx";
import { useStore } from "@/lib/store";
import { useToast } from "@/lib/hooks/useToast";
import type { QueryInputProps } from "@/lib/types";

/**
 * Main query search input where users type questions.
 * Designed with clinical precision for high-trust academic research.
 */
export default function QueryInput({
  onSubmit,
  isLoading,
  disabled = false,
  placeholder = "Ask a question about your documents...",
  maxLength = 500,
  showCharCount = true,
  onClear,
}: QueryInputProps) {
  const { apiKey } = useStore();
  const { toast } = useToast();
  const [value, setValue] = useState("");
  const [mounted, setMounted] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isKeyMissing = mounted ? !apiKey : true;
  const isInputDisabled = disabled || isLoading || isKeyMissing;

  // Auto-resize textarea height between 1 and 6 lines
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineCount = el.value.split("\n").length;
    if (lineCount <= 6) {
      el.style.height = `${el.scrollHeight}px`;
    } else {
      el.style.height = "140px"; // Cap height around 6 lines
    }
  }, [value]);

  const handleClear = useCallback(() => {
    setValue("");
    if (onClear) onClear();
    textareaRef.current?.focus();
  }, [onClear]);

  const handleSubmitInternal = useCallback(() => {
    if (isInputDisabled || !value.trim()) return;
    onSubmit(value.trim());
    setValue("");
    textareaRef.current?.focus();
  }, [onSubmit, value, isInputDisabled]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Escape key: Clear input if not loading
      if (e.key === "Escape" && !isLoading) {
        e.preventDefault();
        handleClear();
        return;
      }

      // Enter (without Shift) or Cmd/Ctrl+Enter to submit
      const isCmdOrCtrlEnter = (e.metaKey || e.ctrlKey) && e.key === "Enter";
      const isStandardEnter = e.key === "Enter" && !e.shiftKey;

      if (isStandardEnter || isCmdOrCtrlEnter) {
        e.preventDefault();
        handleSubmitInternal();
      }
    },
    [isLoading, handleClear, handleSubmitInternal]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const pastedText = e.clipboardData.getData("text");
      if (pastedText.length > maxLength) {
        e.preventDefault();
        const truncated = pastedText.slice(0, maxLength);
        setValue(truncated);
        toast.warning(
          "Input Truncated",
          `Pasted text exceeded the ${maxLength} character limit and was truncated.`
        );
      }
    },
    [maxLength, toast]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setValue(e.target.value.slice(0, maxLength));
    },
    [maxLength]
  );

  const displayCharCount = showCharCount && value.length >= 400;
  const isNearLimit = value.length >= maxLength;

  return (
    <div className="flex flex-col gap-2 pb-4 select-none">
      {/* 1. API Key Warning Indicator */}
      {isKeyMissing && (
        <div 
          id="key-warning"
          role="alert" 
          className="flex items-center gap-1.5 rounded border border-danger/35 bg-danger/5 px-3 py-1.5 text-xs text-danger select-none"
        >
          <AlertCircle size={14} className="shrink-0" />
          <span>An API Key is required to perform queries. Please configure your key in Administration.</span>
        </div>
      )}

      {/* 2. Textarea query container (div + button, no form element) */}
      <div
        className={clsx(
          "relative flex items-end rounded-lg border bg-surface transition-all duration-fast focus-within:bg-white focus-within:shadow-sm focus-within:ring-2 focus-within:ring-accent focus-within:ring-offset-2",
          isKeyMissing 
            ? "border-border opacity-70 cursor-not-allowed" 
            : "border-border focus-within:border-accent"
        )}
      >
        <textarea
          ref={textareaRef}
          role="textbox"
          aria-multiline="true"
          aria-label="Ask a question about your documents"
          aria-describedby="char-count"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          disabled={isInputDisabled}
          rows={1}
          placeholder={
            isKeyMissing 
              ? "Set API key first..." 
              : placeholder
          }
          className="w-full resize-none bg-transparent py-3 pl-4 pr-14 font-sans text-sm text-primary placeholder-muted focus:outline-none disabled:cursor-not-allowed max-h-[140px] no-scrollbar leading-relaxed"
        />

        {/* Submit button inside textarea block */}
        <div className="absolute bottom-2 right-2.5">
          <button
            onClick={handleSubmitInternal}
            disabled={isInputDisabled || !value.trim()}
            aria-label={isLoading ? "Sending query..." : "Send Query"}
            className={clsx(
              "flex h-7 w-7 items-center justify-center rounded-md transition-all duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              value.trim() && !isInputDisabled
                ? "bg-accent text-white hover:bg-accent-hover"
                : "bg-surface-2 text-muted cursor-not-allowed"
            )}
          >
            {isLoading ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <ArrowUp size={14} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {/* 3. Footer Helpers (Character counts and shortcuts) */}
      <div className="flex items-center justify-between text-[10px] text-muted px-1">
        <span aria-live="polite">
          {isLoading && <span className="sr-only">Query is processing. Please wait.</span>}
        </span>
        {displayCharCount && (
          <span 
            id="char-count"
            className={clsx("font-mono font-semibold", isNearLimit ? "text-danger" : "text-secondary")}
          >
            {value.length} / {maxLength}
          </span>
        )}
      </div>
    </div>
  );
}

// Usage:
// <QueryInput
//   onSubmit={handleQuery}
//   isLoading={isLoading}
//   maxLength={500}
//   placeholder="Ask a question..."
// />
