"use client";

import React from "react";
import clsx from "clsx";
import type { SkeletonLoaderProps } from "@/lib/types";

// Self-contained shimmer stylesheet logic
const SHIMMER_CSS = `
  @keyframes shimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }
  .animate-shimmer {
    background: linear-gradient(90deg, #F1F3F5 25%, #E5E7EB 50%, #F1F3F5 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite linear;
  }
  @media (prefers-reduced-motion: reduce) {
    .animate-shimmer {
      animation: none !important;
      background: #E5E7EB !important;
    }
  }
`;

/**
 * Shimmer-based skeleton loader that prevents layout shifts.
 * Supports customizable variants for academic and dashboard widgets.
 */
export default function SkeletonLoader({
  variant,
  count = 1,
  animated = true,
}: SkeletonLoaderProps) {
  const shimmerClass = animated ? "animate-shimmer" : "bg-surface-2";

  // Helper to render multiple copies of a skeleton block
  const renderList = (renderFn: (idx: number) => React.ReactNode) => {
    return Array.from({ length: count }).map((_, idx) => (
      <React.Fragment key={idx}>{renderFn(idx)}</React.Fragment>
    ));
  };

  // 1. Text Line placeholder
  const renderTextLine = () => (
    <div className={clsx("h-3 rounded bg-surface-2", shimmerClass, "w-full")} />
  );

  // 2. Paragraph placeholder
  const renderParagraph = () => (
    <div className="space-y-2.5 w-full">
      <div className={clsx("h-3 rounded bg-surface-2", shimmerClass, "w-[95%]")} />
      <div className={clsx("h-3 rounded bg-surface-2", shimmerClass, "w-[90%]")} />
      <div className={clsx("h-3 rounded bg-surface-2", shimmerClass, "w-[85%]")} />
      <div className={clsx("h-3 rounded bg-surface-2", shimmerClass, "w-[60%]")} />
    </div>
  );

  // 3. Message Bubble placeholder
  const renderMessage = () => (
    <div className="flex items-start gap-3 w-full p-4 border border-border/40 rounded-lg bg-white select-none">
      {/* Avatar block */}
      <div className={clsx("h-8 w-8 rounded-full bg-surface-2 shrink-0", shimmerClass)} />
      {/* Text block */}
      <div className="flex-1 space-y-2">
        <div className={clsx("h-3 rounded bg-surface-2", shimmerClass, "w-[30%]")} />
        <div className={clsx("h-2.5 rounded bg-surface-2", shimmerClass, "w-[85%]")} />
        <div className={clsx("h-2.5 rounded bg-surface-2", shimmerClass, "w-[75%]")} />
      </div>
    </div>
  );

  // 4. Source Card placeholder
  const renderSourceCard = () => (
    <div className="flex flex-col rounded-lg border border-border bg-white p-4 space-y-3 w-full select-none">
      <div className="flex items-center justify-between">
        <div className={clsx("h-3.5 rounded bg-surface-2", shimmerClass, "w-1/3")} />
        <div className={clsx("h-3.5 rounded bg-surface-2", shimmerClass, "w-12")} />
      </div>
      <div className={clsx("h-2 rounded bg-surface-2", shimmerClass, "w-1/4")} />
      <div className="space-y-1.5 pt-1">
        <div className={clsx("h-2.5 rounded bg-surface-2", shimmerClass, "w-full")} />
        <div className={clsx("h-2.5 rounded bg-surface-2", shimmerClass, "w-[95%]")} />
      </div>
    </div>
  );

  // 5. Evidence Column perspective placeholder
  const renderEvidenceColumn = () => (
    <div className="flex flex-col rounded-lg border-l-4 border-l-border/80 border border-y-border border-r-border bg-white p-5 space-y-4 w-full select-none">
      <div className="flex items-center justify-between border-b border-border/20 pb-3">
        <div className={clsx("h-3.5 rounded bg-surface-2", shimmerClass, "w-1/3")} />
        <div className={clsx("h-3.5 rounded bg-surface-2", shimmerClass, "w-16")} />
      </div>
      <div className={clsx("h-2 rounded bg-surface-2", shimmerClass, "w-1/4")} />
      <div className="space-y-2">
        <div className={clsx("h-2.5 rounded bg-surface-2", shimmerClass, "w-[90%]")} />
        <div className={clsx("h-2.5 rounded bg-surface-2", shimmerClass, "w-[95%]")} />
        <div className={clsx("h-2.5 rounded bg-surface-2", shimmerClass, "w-[70%]")} />
      </div>
      <div className={clsx("h-8 rounded bg-surface-2 w-full mt-2", shimmerClass)} />
    </div>
  );

  // 6. Metrics Card grid placeholder
  const renderMetricsGrid = () => (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full select-none">
      {Array.from({ length: 3 }).map((_, idx) => (
        <div key={idx} className="flex flex-col rounded-lg border border-border bg-white p-4 space-y-3 shadow-sm">
          <div className={clsx("h-3 rounded bg-surface-2", shimmerClass, "w-1/2")} />
          <div className={clsx("h-6 rounded bg-surface-2", shimmerClass, "w-1/3")} />
          <div className={clsx("h-2 rounded bg-surface-2", shimmerClass, "w-3/4")} />
        </div>
      ))}
    </div>
  );

  // 7. Full CA-RAG response layout placeholder
  const renderCARAGResponse = () => (
    <div className="flex flex-col space-y-5 w-full select-none">
      {/* Banner placeholder */}
      <div className={clsx("h-11 rounded-lg border border-border bg-surface-2", shimmerClass, "w-full")} />
      {/* Tab bar placeholder */}
      <div className="flex items-center gap-2">
        <div className={clsx("h-7 rounded bg-surface-2", shimmerClass, "w-20")} />
        <div className={clsx("h-7 rounded bg-surface-2", shimmerClass, "w-20")} />
      </div>
      {/* Two columns side-by-side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {renderEvidenceColumn()}
        {renderEvidenceColumn()}
      </div>
    </div>
  );

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: SHIMMER_CSS }} />
      <div className="w-full">
        {renderList((idx) => {
          switch (variant) {
            case "text-line":
              return renderTextLine();
            case "paragraph":
              return renderParagraph();
            case "message":
              return renderMessage();
            case "source-card":
              return renderSourceCard();
            case "evidence-column":
              return renderEvidenceColumn();
            case "metrics-grid":
              return renderMetricsGrid();
            case "ca-rag-response":
              return renderCARAGResponse();
            default:
              return renderTextLine();
          }
        })}
      </div>
    </>
  );
}

// Usage:
// <SkeletonLoader variant="ca-rag-response" animated={true} />
