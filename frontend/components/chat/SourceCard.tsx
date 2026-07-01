"use client";

import React, { memo, useState, useCallback, useEffect, useRef } from "react";
import { FileText, Star, ChevronDown, ChevronUp } from "lucide-react";
import clsx from "clsx";
import type { SourceCardProps } from "@/lib/types";

/**
 * Metadata card representing a single document chunk retrieval source.
 * Supports highlighting, collapsing, and dynamic relevance indicators.
 */
const SourceCard = memo(function SourceCard({
  source,
  isActive = false,
  clusterColor,
  onExpand,
  rank,
  isContradicting = false,
  isLoading = false,
}: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  // Auto-expand card if active (e.g. from citation click)
  useEffect(() => {
    if (isActive) {
      setExpanded(true);
      cardRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [isActive]);

  const handleToggle = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev;
      if (next && onExpand) {
        onExpand();
      }
      return next;
    });
  }, [onExpand]);

  if (isLoading) {
    return (
      <div className="flex flex-col rounded-lg border border-border bg-white p-4 animate-pulse space-y-3">
        <div className="flex items-center gap-3">
          <div className="h-4 w-6 bg-surface-2 rounded" />
          <div className="h-4 w-40 bg-surface-2 rounded" />
        </div>
        <div className="h-3 w-1/3 bg-surface-2 rounded" />
        <div className="h-10 w-full bg-surface-2 rounded" />
      </div>
    );
  }

  // Safely extract metadata fields
  const metadata = source.metadata || {};
  const docTitle = metadata.title || source.chunk_id;
  const chunkIndex = metadata.chunk_index ?? 1;
  const totalChunks = metadata.total_chunks ?? 1;
  const docCategory = metadata.category || metadata.file_type || "Document";

  // Calculate stars based on metadata quality or retrieval score
  const qualityScore = metadata.quality_score ?? source.score;
  const starCount = Math.max(1, Math.min(Math.round(qualityScore * 5), 5));

  // Relevance representation (score from 0.0 to 1.0)
  const relevancePct = Math.max(0, Math.min(source.score * 100, 100));
  const filledBlocks = Math.round(source.score * 10);

  return (
    <div
      ref={cardRef}
      onClick={handleToggle}
      className={clsx(
        "flex flex-col rounded-lg border bg-white p-4 shadow-sm transition-all duration-base cursor-pointer select-none",
        // Contradicting state has priority styling
        isContradicting && [
          "border-l-4 border-l-danger",
          isActive ? "bg-danger/5 border-y-danger border-r-danger" : "border-border hover:bg-danger/[0.02]"
        ],
        // Standard active vs hover styling
        !isContradicting && [
          isActive 
            ? "border-l-4 border-l-accent border-y-accent/30 border-r-accent/30 bg-citation/40" 
            : "border-border hover:bg-surface"
        ]
      )}
    >
      {/* 1. Header Information */}
      <div className="flex items-start justify-between gap-3 border-b border-border/40 pb-2 mb-3">
        <div className="flex items-start gap-2.5 truncate">
          <span className="font-mono text-xs font-bold text-muted mt-0.5">#{rank}</span>
          <FileText size={16} className="text-secondary mt-0.5 shrink-0" />
          <div className="truncate">
            <h4 className="font-sans text-xs font-bold text-primary truncate select-text leading-tight">
              {docTitle}
            </h4>
            <span className="font-sans text-[10px] text-muted">
              Chunk {chunkIndex} of {totalChunks}
            </span>
          </div>
        </div>

        {/* Dynamic Category Tag */}
        <span className="inline-flex rounded bg-surface-2 px-1.5 py-0.5 text-[9px] font-bold text-secondary uppercase border border-border/60 shrink-0 select-none">
          {docCategory}
        </span>
      </div>

      {/* 2. Visual Scores and Stars */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-secondary font-sans mb-3 select-none">
        {/* Relevance Block Bar */}
        <div className="flex items-center gap-1.5">
          <span className="font-bold">Relevance:</span>
          <span className="font-mono tracking-tighter text-accent font-semibold">
            {"█".repeat(filledBlocks)}
            {"░".repeat(Math.max(0, 10 - filledBlocks))}
          </span>
          <span className="font-mono font-bold">{(source.score).toFixed(2)}</span>
        </div>

        {/* Quality Stars */}
        <div className="flex items-center gap-1">
          <span className="font-bold">Quality:</span>
          <span className="inline-flex text-warning">
            {Array.from({ length: 5 }).map((_, idx) => (
              <Star
                key={idx}
                size={10}
                fill={idx < starCount ? "currentColor" : "none"}
                className="shrink-0"
              />
            ))}
          </span>
        </div>
      </div>

      {/* 3. Collapsible Body Text */}
      <div className="relative font-sans text-xs leading-relaxed text-secondary select-text">
        <p className={clsx("transition-all duration-base", !expanded && "line-clamp-3")}>
          {source.text}
        </p>

        {/* Show More/Less toggle indicator */}
        <div className="flex justify-end mt-2 pt-1 border-t border-border/20 select-none">
          <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase text-accent hover:text-accent-hover tracking-wider">
            {expanded ? (
              <>
                <span>Show less</span>
                <ChevronUp size={12} />
              </>
            ) : (
              <>
                <span>Show more</span>
                <ChevronDown size={12} />
              </>
            )}
          </span>
        </div>
      </div>
    </div>
  );
});

export default SourceCard;

// Usage:
// <SourceCard
//   source={sourceObj}
//   rank={1}
//   isActive={true}
//   isContradicting={false}
// />
