"use client";

import React, { memo, useCallback } from "react";
import clsx from "clsx";
import type { CitationPillProps } from "@/lib/types";

/**
 * Performance-optimized inline citation reference pill.
 * Integrates pure CSS tooltips and highlights active source states.
 */
const CitationPill = memo(function CitationPill({
  docTitle,
  chunkId,
  docId,
  claimId,
  onClick,
  isActive = false,
  isContradicting = false,
  excerpt = "No excerpt context available.",
}: CitationPillProps) {
  const handleOnClick = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      if (onClick) {
        onClick(chunkId);
      }
    },
    [onClick, chunkId]
  );

  const truncatedTitle = docTitle.length > 20 ? `${docTitle.slice(0, 20)}...` : docTitle;
  const tooltipText = `${docTitle} | Chunk: ${chunkId.split("-").pop() || chunkId}\n\n"${excerpt.slice(0, 120)}${excerpt.length > 120 ? "..." : ""}"`;

  return (
    <span className="relative group inline-flex items-center">
      {/* Interactive Citation Button */}
      <button
        onClick={handleOnClick}
        aria-label={`Citation: ${docTitle}, chunk ${chunkId}. Click to view source.`}
        className={clsx(
          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-sans text-[10px] font-semibold transition-all duration-fast select-none cursor-pointer border focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent",
          // Contradicting state styling
          isContradicting && [
            isActive
              ? "bg-danger text-white border-danger shadow-sm scale-105"
              : "bg-danger/10 text-danger border-danger/20 hover:bg-danger/20"
          ],
          // Active vs normal standard state styling
          !isContradicting && [
            isActive
              ? "bg-citation border-citation-border text-accent font-bold ring-2 ring-accent/30 shadow-sm scale-105"
              : "bg-citation text-secondary border-citation-border hover:bg-citation/70"
          ]
        )}
      >
        {isContradicting && <span aria-hidden="true">⚡</span>}
        <span>
          {truncatedTitle}
        </span>
        <span className="opacity-50 mx-0.5">|</span>
        <span>
          {chunkId.split("-").pop() || chunkId}
        </span>
      </button>

      {/* Pure CSS Tooltip positioning */}
      <div 
        role="tooltip"
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-[60] w-64 p-3 rounded-lg bg-accent text-white shadow-lg text-[10px] leading-relaxed border border-border/10 pointer-events-none transition-all duration-fast select-text"
      >
        <div className="font-bold border-b border-white/10 pb-1 mb-1 truncate">
          {docTitle}
        </div>
        <p className="italic text-white/90">
          &ldquo;{excerpt.slice(0, 100)}{excerpt.length > 100 ? "..." : ""}&rdquo;
        </p>
        <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-accent" />
      </div>
    </span>
  );
});

export default CitationPill;

// Usage:
// <CitationPill
//   docTitle="Optimal RAG Chunk Size"
//   chunkId="chunk-3"
//   docId="doc-001"
//   excerpt="Retrieval models perform best with 100-word chunks."
//   onClick={handleCitationClick}
// />
