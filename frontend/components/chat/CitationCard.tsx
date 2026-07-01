"use client";
import React, { useRef, useEffect } from "react";
import { Source } from "@/lib/types";
import { useStore } from "@/lib/store";
import { X, ExternalLink } from "lucide-react";

interface CitationCardProps {
  source: Source;
  index: number;
  onClose: () => void;
}

export default function CitationCard({ source, index, onClose }: CitationCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const { setCurrentSources } = useStore();

  // Escape key and click outside listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    
    const handleClickOutside = (e: MouseEvent) => {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("mousedown", handleClickOutside);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("mousedown", handleClickOutside);
    };
  }, [onClose]);

  const docTitle = source.metadata?.title || "Document Chunk";
  const chunkId = source.chunk_id;
  const excerpt = source.text.slice(0, 150) + (source.text.length > 150 ? "..." : "");

  return (
    <div
      ref={cardRef}
      className="absolute z-40 mt-1 w-80 rounded-md border border-border bg-white p-3.5 shadow-lg text-primary select-text focus-visible:outline-none"
      style={{ 
        top: "100%", 
        left: "50%", 
        transform: "translateX(-50%)",
        lineHeight: "1.4"
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Title block */}
      <div className="flex items-start justify-between gap-3 border-b border-border pb-1.5 mb-2 select-none">
        <div className="overflow-hidden">
          <span className="font-sans text-xs font-bold text-primary block truncate">
            [{index}] {docTitle}
          </span>
          <span className="font-mono text-[9px] text-muted block mt-0.5 truncate">
            CHUNK: {chunkId}
          </span>
        </div>
        <button
          onClick={onClose}
          className="rounded p-0.5 text-muted hover:bg-surface-2 hover:text-primary transition-colors"
          aria-label="Dismiss citation popup"
        >
          <X size={12} />
        </button>
      </div>

      {/* Quote summary excerpt */}
      <p className="font-sans text-xs text-secondary italic mb-3 select-text">
        "{excerpt}"
      </p>

      {/* Bottom Panel Actions */}
      <div className="flex items-center justify-between border-t border-border/40 pt-2 select-none">
        <span className="font-sans text-[10px] text-muted">
          Relevance: {source.score.toFixed(3)}
        </span>
        <button
          onClick={() => {
            setCurrentSources([source]);
            onClose();
          }}
          className="flex items-center gap-1 font-sans text-xs font-bold text-accent hover:text-accent-hover transition-colors"
        >
          <span>View in Sources</span>
          <ExternalLink size={10} />
        </button>
      </div>
    </div>
  );
}
