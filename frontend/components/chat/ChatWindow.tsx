"use client";
import React, { useEffect, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import MessageBubble from "./MessageBubble";
import EmptyState from "./EmptyState";
import { ArrowDown } from "lucide-react";

export default function ChatWindow() {
  const { messages, isLoading } = useStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // Auto scroll to bottom
  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Track scroll position to show/hide "Scroll to bottom" button
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 150;
    setShowScrollBtn(!isAtBottom);
  };

  // Group messages by day
  const formatDateSeparator = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleDateString(undefined, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric"
    });
  };

  if (messages.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      {/* Scrollable messages area */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto space-y-6 pb-6 pr-2 no-scrollbar"
      >
        {messages.map((message, index) => {
          const prevMsg = messages[index - 1];
          const isNewDay =
            !prevMsg ||
            new Date(prevMsg.timestamp).toDateString() !==
              new Date(message.timestamp).toDateString();

          return (
            <React.Fragment key={message.id}>
              {/* Date Separator */}
              {isNewDay && (
                <div className="my-6 flex justify-center">
                  <span className="bg-surface px-3 py-1 font-sans text-xs font-semibold text-secondary rounded-full border border-border select-none">
                    {formatDateSeparator(message.timestamp)}
                  </span>
                </div>
              )}
              <MessageBubble message={message} />
            </React.Fragment>
          );
        })}
      </div>

      {/* Floating scroll to bottom button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 flex h-8 w-8 items-center justify-center rounded-full border border-border bg-white text-secondary shadow-md hover:bg-surface-2 hover:text-primary transition-all duration-fast z-10"
          aria-label="Scroll to bottom"
        >
          <ArrowDown size={14} />
        </button>
      )}
    </div>
  );
}
