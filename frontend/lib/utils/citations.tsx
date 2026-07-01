import React from "react";
import { Source } from "@/lib/types";
import CitationCard from "@/components/chat/CitationCard";

interface CitationPillProps {
  source: Source;
  index: number;
}

// We define a client-side component to handle opening/closing of individual citation cards
export function CitationPill({ source, index }: CitationPillProps) {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <span className="relative inline-block select-none">
      <button
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className="mx-0.5 px-1.5 py-0.5 rounded bg-citation border border-citation-border font-sans text-xs font-bold text-accent hover:bg-accent hover:text-white hover:border-accent transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        aria-label={`Citation [${index}]`}
        type="button"
      >
        [{index}]
      </button>
      {isOpen && (
        <CitationCard
          source={source}
          index={index}
          onClose={() => setIsOpen(false)}
        />
      )}
    </span>
  );
}

/**
 * Parses RAG system answer text to convert raw citation markers to interactive citation pills.
 * Matches:
 * - Numeric brackets: [1], [2]
 * - Custom format brackets: [Doc: xyz | Chunk: abc]
 */
export function parseCitations(text: string, sources: Source[]): React.ReactNode[] {
  if (!text) return [];

  // Match [1], [2], or [Doc: ... | Chunk: ...]
  const regex = /(\[\d+\]|\[Doc:\s*[^\|\]]+\|\s*Chunk:\s*[^\]]+\])/g;
  const parts = text.split(regex);
  
  if (parts.length <= 1) {
    return [React.createElement("span", { key: "text" }, text)];
  }

  return parts.map((part, i) => {
    // If it doesn't match the regex, just return the text
    if (!part.match(regex)) {
      return React.createElement("span", { key: `text-${i}` }, part);
    }

    // 1. Check if it's numeric format like [1]
    const numericMatch = part.match(/^\[(\d+)\]$/);
    if (numericMatch) {
      const index = parseInt(numericMatch[1], 10);
      if (index >= 1 && index <= sources.length) {
        const source = sources[index - 1];
        return React.createElement(CitationPill, {
          key: `citation-${i}`,
          source,
          index,
        });
      }
    }

    // 2. Check if it's custom format like [Doc: doc_id | Chunk: chunk_id]
    const docChunkMatch = part.match(/Chunk:\s*([^\s\]]+)/);
    if (docChunkMatch) {
      const chunkId = docChunkMatch[1];
      // Search in sources for matching chunk_id
      const sourceIndex = sources.findIndex((s) => s.chunk_id === chunkId);
      if (sourceIndex !== -1) {
        return React.createElement(CitationPill, {
          key: `citation-${i}`,
          source: sources[sourceIndex],
          index: sourceIndex + 1,
        });
      }
    }

    // Fallback: If no match found in our sources list, return the raw marker
    return React.createElement("span", { key: `text-fallback-${i}` }, part);
  });
}
