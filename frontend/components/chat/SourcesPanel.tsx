"use client";
import React, { useState, useEffect, useRef } from "react";
import { useStore } from "@/lib/store";
import { X, FileText, ChevronDown, ChevronUp, Copy, Check } from "lucide-react";
import clsx from "clsx";

interface SourcesPanelProps {
  onClose: () => void;
}

export default function SourcesPanel({ onClose }: SourcesPanelProps) {
  const { currentSources } = useStore();
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Copy excerpt to clipboard helper
  const handleCopyText = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleExpand = (id: string) => {
    setExpandedCards((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="flex h-full flex-col bg-surface font-sans text-primary">
      {/* 1. Header */}
      <div className="flex h-14 items-center justify-between border-b border-border px-4 bg-white select-none">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-accent" />
          <span className="font-sans text-sm font-bold text-primary">
            Retrieved Evidence ({currentSources.length})
          </span>
        </div>
        <button
          onClick={onClose}
          className="rounded p-1 text-secondary hover:bg-surface-2 transition-colors"
          aria-label="Close panel"
        >
          <X size={16} />
        </button>
      </div>

      {/* 2. Sources Cards List */}
      <div 
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 no-scrollbar"
      >
        {currentSources.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center select-none">
            <FileText size={32} className="text-muted mb-2" />
            <span className="font-sans text-xs font-semibold text-secondary">No Sources Loaded</span>
            <p className="font-sans text-[11px] text-muted max-w-[200px] mt-1">
              Select or click on citation markers within answers to review source records.
            </p>
          </div>
        ) : (
          currentSources.map((src, index) => {
            const docTitle = src.metadata?.title || "Document Chunk";
            const chunkId = src.chunk_id;
            const score = src.score;
            const isExpanded = !!expandedCards[chunkId];
            
            // Normalize distance score to percentage bar (typical distances are 0.1 to 1.5, smaller = closer)
            // Let's invert it for visualization where longer bar = higher relevance
            const relPct = Math.max(0, Math.min(100, Math.round((1.5 - Math.min(1.5, score)) / 1.5 * 100)));

            return (
              <div
                key={chunkId}
                id={`source-card-${chunkId}`}
                className="group rounded-md border border-border bg-white p-3.5 shadow-sm hover:border-border-strong transition-all duration-fast select-text"
              >
                {/* Document Meta Row */}
                <div className="flex items-start justify-between gap-2 border-b border-border/40 pb-2 mb-2 select-none">
                  <div className="overflow-hidden">
                    <span className="font-sans text-xs font-bold text-primary block truncate" title={docTitle}>
                      [{index + 1}] {docTitle}
                    </span>
                    <span className="font-mono text-[9px] text-muted block mt-0.5 truncate">
                      ID: {chunkId}
                    </span>
                  </div>
                  
                  {/* Actions */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => handleCopyText(chunkId, src.text)}
                      className="rounded p-1 text-muted hover:bg-surface-2 hover:text-primary transition-colors"
                      title="Copy chunk excerpt"
                    >
                      {copiedId === chunkId ? <Check size={11} className="text-success" /> : <Copy size={11} />}
                    </button>
                    <button
                      onClick={() => toggleExpand(chunkId)}
                      className="rounded p-1 text-muted hover:bg-surface-2 hover:text-primary transition-colors"
                    >
                      {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                    </button>
                  </div>
                </div>

                {/* Score bar */}
                <div className="flex items-center gap-2 mb-2.5 select-none">
                  <span className="font-sans text-[10px] text-secondary font-medium w-14 shrink-0">
                    Relevance:
                  </span>
                  <div className="flex-1 h-1.5 bg-surface-2 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-accent rounded-full" 
                      style={{ width: `${relPct}%` }}
                    />
                  </div>
                  <span className="font-mono text-[10px] text-primary font-semibold w-8 text-right shrink-0">
                    {score.toFixed(3)}
                  </span>
                </div>

                {/* Text excerpt container */}
                <p 
                  className={clsx(
                    "font-sans text-xs text-secondary leading-relaxed",
                    !isExpanded && "line-clamp-4"
                  )}
                >
                  {src.text}
                </p>

                {/* Metadata tags */}
                {isExpanded && src.metadata && (
                  <div className="mt-3 pt-2.5 border-t border-border/40 select-none">
                    <span className="font-sans text-[10px] font-bold text-muted block mb-1">
                      CHROMA METADATA:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(src.metadata)
                        .filter(([k]) => k !== "title")
                        .map(([k, v]) => (
                          <div 
                            key={k} 
                            className="bg-surface-2 px-1.5 py-0.5 rounded border border-border font-mono text-[9px] text-secondary"
                          >
                            {k}: {String(v)}
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
