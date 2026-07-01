"use client";

import React from "react";
import { 
  FileSearch, 
  UploadCloud, 
  ShieldCheck, 
  Search, 
  AlertTriangle, 
  WifiOff, 
  ChevronRight 
} from "lucide-react";
import clsx from "clsx";
import type { EmptyStateProps, EmptyStateVariant } from "@/lib/types";

// Default content mappings for all variants
const VARIANT_CONFIGS: Record<
  EmptyStateVariant,
  {
    icon: React.ReactNode;
    title: string;
    description: string;
  }
> = {
  "no-messages": {
    icon: <FileSearch size={48} className="text-muted" />,
    title: "Ask your documents anything",
    description: "Upload documents first, then ask questions. Every answer cites its sources.",
  },
  "no-documents": {
    icon: <UploadCloud size={48} className="text-muted" />,
    title: "No documents indexed yet",
    description: "Upload PDFs or markdown files to get started.",
  },
  "no-results": {
    icon: <Search size={48} className="text-muted" />,
    title: "No results found",
    description: "Your query did not return any matches in the indexed documents.",
  },
  "no-contradictions": {
    icon: <ShieldCheck size={48} className="text-muted" />,
    title: "Sources are in agreement",
    description: "No contradictions detected across retrieved documents.",
  },
  error: {
    icon: <AlertTriangle size={48} className="text-muted" />,
    title: "Something went wrong",
    description: "An unexpected error occurred while processing the request.",
  },
  offline: {
    icon: <WifiOff size={48} className="text-muted" />,
    title: "System is offline",
    description: "Unable to reach the backend RAG API servers. Please check your connection.",
  },
};

const DEFAULT_CHIPS = [
  "What chunk size is optimal for RAG?",
  "Compare dense vs sparse retrieval",
  "What is the recommended Redis cluster size?",
];

/**
 * Centered empty state placeholder with guidelines and prompt shortcuts.
 * Designed with a white contrast academic journal aesthetic.
 */
export default function EmptyState({
  variant,
  title,
  description,
  action,
  secondaryAction,
  exampleChips = DEFAULT_CHIPS,
}: EmptyStateProps) {
  const config = VARIANT_CONFIGS[variant] || VARIANT_CONFIGS.error;
  const displayTitle = title || config.title;
  const displayDescription = description || config.description;

  return (
    <div className="flex flex-col items-center justify-center text-center max-w-sm mx-auto py-12 px-6 select-none">
      {/* 1. Muted Icon Area */}
      <div className="mb-4 text-secondary/60 shrink-0" aria-hidden="true">
        {config.icon}
      </div>

      {/* 2. Structured Metadata Text */}
      <h3 className="font-sans text-base font-semibold text-primary mb-2 select-text leading-snug">
        {displayTitle}
      </h3>
      <p className="font-sans text-xs text-secondary leading-relaxed mb-6 select-text">
        {displayDescription}
      </p>

      {/* 3. Action Buttons & Chips */}
      {variant === "no-messages" && exampleChips.length > 0 && (
        <div className="w-full space-y-2 select-none">
          <span className="font-sans text-[10px] font-bold text-muted uppercase tracking-wider block">
            Suggested Queries
          </span>
          <div className="flex flex-col gap-1.5 pt-1">
            {exampleChips.map((chip, idx) => (
              <button
                key={idx}
                onClick={() => {
                  // Direct typing emulation hook if supported
                  const textarea = document.querySelector("textarea");
                  if (textarea) {
                    const nativeTextareaValueSetter = Object.getOwnPropertyDescriptor(
                      HTMLTextAreaElement.prototype,
                      "value"
                    )?.set;
                    nativeTextareaValueSetter?.call(textarea, chip);
                    textarea.dispatchEvent(new Event("input", { bubbles: true }));
                    textarea.focus();
                  }
                }}
                className="inline-flex items-center justify-between rounded-lg border border-border bg-white px-3.5 py-2 text-left font-sans text-xs text-secondary hover:bg-surface hover:text-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition-all duration-fast select-none cursor-pointer group"
              >
                <span className="truncate pr-2 font-medium">{chip}</span>
                <ChevronRight size={12} className="text-muted group-hover:text-accent shrink-0 transition-transform duration-fast transform group-hover:translate-x-0.5" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Primary and secondary button links */}
      {(action || secondaryAction) && (
        <div className="flex flex-col gap-2.5 w-full select-none">
          {action && (
            <button
              onClick={action.onClick}
              className="w-full rounded-md bg-accent px-4 py-2 font-sans text-xs font-semibold text-white hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 transition-all duration-fast select-none cursor-pointer shadow-sm"
            >
              {action.label}
            </button>
          )}

          {secondaryAction && (
            <button
              onClick={secondaryAction.onClick}
              className="w-full rounded-md border border-border bg-white px-4 py-2 font-sans text-xs font-semibold text-secondary hover:bg-surface focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent transition-all duration-fast select-none cursor-pointer"
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// Usage:
// <EmptyState
//   variant="no-documents"
//   action={{ label: "Upload Documents", onClick: openDropZone }}
// />
