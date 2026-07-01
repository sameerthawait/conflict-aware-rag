"use client";

import React, { memo, useState, useCallback } from "react";
import { ChevronDown, ChevronUp, Star, Info } from "lucide-react";
import clsx from "clsx";
import CitationPill from "../chat/CitationPill";
import type { EvidenceColumnProps } from "@/lib/types";

// Helper color configuration matching perspective rules
const PERSPECTIVE_CONFIG = {
  A: {
    borderClass: "border-accent",
    dotClass: "bg-accent",
    textClass: "text-accent",
    bgClass: "bg-accent/5",
  },
  B: {
    borderClass: "border-[#7C3AED]",
    dotClass: "bg-[#7C3AED]",
    textClass: "text-[#7C3AED]",
    bgClass: "bg-[#7C3AED]/5",
  },
  C: {
    borderClass: "border-[#0891B2]",
    dotClass: "bg-[#0891B2]",
    textClass: "text-[#0891B2]",
    bgClass: "bg-[#0891B2]/5",
  },
  D: {
    borderClass: "border-[#B45309]",
    dotClass: "bg-[#B45309]",
    textClass: "text-[#B45309]",
    bgClass: "bg-[#B45309]/5",
  },
};

const EvidenceColumn = memo(function EvidenceColumn({
  cluster,
  perspective,
  isHighlighted = false,
  onClaimClick,
  onSourceClick,
  isLoading = false,
}: EvidenceColumnProps) {
  const [sourcesExpanded, setSourcesExpanded] = useState(false);

  const toggleSources = useCallback(() => {
    setSourcesExpanded((prev) => !prev);
  }, []);

  const config = PERSPECTIVE_CONFIG[perspective] || PERSPECTIVE_CONFIG.A;

  if (isLoading) {
    return (
      <div className="flex flex-col rounded-lg border border-border bg-white p-5 animate-pulse space-y-4">
        <div className="h-6 w-2/3 bg-surface-2 rounded" />
        <div className="h-4 w-1/2 bg-surface-2 rounded" />
        <div className="space-y-2 pt-2">
          <div className="h-3 w-full bg-surface-2 rounded" />
          <div className="h-3 w-5/6 bg-surface-2 rounded" />
          <div className="h-3 w-4/5 bg-surface-2 rounded" />
        </div>
      </div>
    );
  }

  // Handle empty perspective clusters
  if (!cluster || !cluster.perspectives || cluster.perspectives.length === 0) {
    return (
      <div 
        className={clsx(
          "flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface p-8 text-center text-secondary min-h-[200px] select-none",
          isHighlighted && "bg-surface-2 shadow-sm"
        )}
      >
        <Info size={24} className="text-muted mb-2" />
        <p className="font-sans text-xs font-semibold">No evidence for Perspective {perspective}</p>
      </div>
    );
  }

  // Calculate confidence bar details
  const confidenceVal = cluster.avg_confidence || 0.0;
  const barWidth = `${Math.min(confidenceVal * 100, 100)}%`;

  // Render confidence star icons based on text description
  const renderConfidenceStars = (level: string) => {
    const starCount = level.toLowerCase() === "high" ? 5 : (level.toLowerCase() === "medium" ? 3 : 1);
    return (
      <span className="inline-flex gap-0.5 text-warning" aria-label={`${starCount} out of 5 confidence stars`}>
        {Array.from({ length: 5 }).map((_, idx) => (
          <Star 
            key={idx} 
            size={10} 
            fill={idx < starCount ? "currentColor" : "none"} 
            className="shrink-0"
          />
        ))}
      </span>
    );
  };

  return (
    <div
      className={clsx(
        "flex flex-col rounded-lg border-l-4 border border-y-border border-r-border bg-white p-5 shadow-sm transition-all duration-base select-none",
        config.borderClass,
        isHighlighted && ["shadow-md ring-1 ring-accent/15", config.bgClass]
      )}
    >
      {/* 1. Header Details */}
      <div className="border-b border-border/40 pb-3 mb-4 select-none">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={clsx("h-2.5 w-2.5 rounded-full shrink-0", config.dotClass)} />
            <span className={clsx("font-sans text-xs font-bold uppercase tracking-wider", config.textClass)}>
              Perspective {perspective}
            </span>
          </div>
          <span className="inline-flex items-center rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-bold text-secondary border border-border">
            {cluster.chunk_count} sources
          </span>
        </div>

        <h3 className="font-sans text-sm font-bold text-primary mt-2 select-text leading-snug">
          {cluster.label}
        </h3>

        {/* Confidence metric indicator */}
        <div className="flex items-center gap-2 mt-3 select-none">
          <div className="h-1.5 w-20 rounded-full bg-surface-2 overflow-hidden border border-border shrink-0">
            <div className={clsx("h-full rounded-full", config.dotClass)} style={{ width: barWidth }} />
          </div>
          <span className="font-mono text-[10px] font-bold text-secondary">
            {confidenceVal.toFixed(2)} confidence
          </span>
        </div>
      </div>

      {/* 2. Body Claims Excerpt */}
      <div className="flex-1 space-y-4 font-sans text-xs leading-relaxed text-secondary select-text mb-4">
        {cluster.perspectives.map((p, idx) => (
          <div 
            key={idx} 
            className="border-b border-border/20 last:border-b-0 pb-3 last:pb-0 cursor-pointer group"
            onClick={() => onClaimClick && onClaimClick(p.chunk_id)}
          >
            <div className="font-bold text-primary mb-1 inline-flex items-center gap-1 group-hover:text-accent transition-colors">
              <span>Stance:</span>
              <span className="font-semibold text-secondary">{p.stance_label}</span>
            </div>
            
            <p className="mb-2 italic">
              &ldquo;{p.key_evidence}&rdquo;
            </p>

            {p.caveats && (
              <p className="text-[10px] text-muted mb-2">
                <span className="font-semibold">Caveat:</span> {p.caveats}
              </p>
            )}

            <div className="flex items-center justify-between mt-2 select-none">
              {renderConfidenceStars(p.source_confidence)}
              <CitationPill
                docTitle={p.source}
                chunkId={p.chunk_id}
                docId={p.chunk_id}
                excerpt={p.key_evidence}
                onClick={onSourceClick}
              />
            </div>
          </div>
        ))}
      </div>

      {/* 3. Collapsible Sources section */}
      <div className="border-t border-border/40 pt-3 select-none">
        <button
          onClick={toggleSources}
          className="flex items-center justify-between w-full font-sans text-[11px] font-bold text-secondary uppercase tracking-wider hover:text-primary transition-colors"
          aria-expanded={sourcesExpanded}
        >
          <span>Sources Cited</span>
          {sourcesExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {sourcesExpanded && (
          <ul className="mt-2 space-y-1.5 font-sans text-[11px] text-secondary select-text pl-1 transition-all duration-base">
            {cluster.perspectives.map((p, idx) => (
              <li 
                key={idx}
                className="flex items-center justify-between py-1 border-b border-border/20 last:border-0"
              >
                <span className="font-medium truncate pr-2 max-w-[160px]">{p.source}</span>
                <span className="shrink-0 scale-90">{renderConfidenceStars(p.source_confidence)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
});

export default EvidenceColumn;

// Usage:
// <EvidenceColumn
//   cluster={clusterData}
//   perspective="A"
//   onSourceClick={handleSourceSelect}
//   totalClusters={2}
// />
