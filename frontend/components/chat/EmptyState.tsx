"use client";
import React from "react";
import { useStore } from "@/lib/store";
import { Search, FileText, CornerDownRight } from "lucide-react";

export default function EmptyState() {
  const { setInputValue } = useStore();

  const exampleQueries = [
    "How does the hybrid retriever fuse search scores?",
    "What is the token cost pricing configuration?",
    "How to rotate and invalidate keys?"
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center text-center p-6 select-none max-w-2xl mx-auto my-auto">
      {/* Visual Doc/Search Icon (Standard SVG layout) */}
      <div className="relative mb-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-border bg-surface shadow-sm">
          <FileText size={32} className="text-accent" />
        </div>
        <div className="absolute -bottom-1.5 -right-1.5 flex h-7 w-7 items-center justify-center rounded-full border border-border bg-white text-secondary shadow-sm">
          <Search size={12} />
        </div>
      </div>

      {/* Header and Subtext */}
      <h2 className="font-sans text-xl font-bold text-primary mb-2">
        Ask your documents anything
      </h2>
      <p className="font-sans text-sm text-secondary leading-relaxed max-w-md mb-8">
        Upload PDF, DOCX, Markdown, or text documents in the Documents manager. 
        Then write query requests below. Generated responses will cite specific sources.
      </p>

      {/* Suggested Prompt Chips */}
      <div className="w-full space-y-2">
        <span className="font-sans text-[11px] font-bold text-muted block text-left mb-2.5">
          SUGGESTED DISCOVERY QUERIES:
        </span>
        <div className="flex flex-col gap-2">
          {exampleQueries.map((query, index) => (
            <button
              key={index}
              onClick={() => setInputValue(query)}
              className="flex items-center justify-between rounded-md border border-border bg-white px-4 py-3 font-sans text-xs font-semibold text-secondary hover:bg-surface hover:text-primary hover:border-border-strong text-left transition-all duration-fast"
            >
              <span>{query}</span>
              <CornerDownRight size={12} className="text-muted shrink-0 ml-2" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
