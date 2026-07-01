"use client";
import React, { useState } from "react";
import { ChatMessage, ConfidenceLevel } from "@/lib/types";
import { useStore } from "@/lib/store";
import { parseCitations } from "@/lib/utils/citations";
import { formatLatency } from "@/lib/utils/formatters";
import ConfidenceBadge from "./ConfidenceBadge";
import GateStatusBar from "./GateStatusBar";
import MultiPerspectiveAnswer from "./MultiPerspectiveAnswer";
import CARAGResponse from "../ca_rag/CARAGResponse";
import { 
  AlertTriangle, 
  ChevronDown, 
  ChevronUp, 
  BookOpen, 
  Clock 
} from "lucide-react";
import clsx from "clsx";

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const { setCurrentSources } = useStore();
  const [isSourcesExpanded, setIsSourcesExpanded] = useState(false);

  const { role, content, response, timestamp, id } = message;
  const isUser = role === "user";
  const isLoadingState = id === "loading";

  // 1. Render User Message
  if (isUser) {
    return (
      <div className="flex justify-end w-full px-4">
        <div className="flex flex-col items-end max-w-[80%]">
          <p className="font-sans text-base text-primary whitespace-pre-wrap selection:bg-accent selection:text-white">
            {content}
          </p>
          <span className="mt-1 font-sans text-xs text-muted select-none">
            {new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
      </div>
    );
  }

  // 2. Render Loading State Bubble
  if (isLoadingState) {
    return (
      <div className="flex flex-col gap-2 w-full max-w-4xl mx-auto px-6 py-4 border border-border bg-surface rounded-lg">
        <div className="flex items-center gap-3">
          <div className="flex space-x-1.5 items-center">
            <div className="h-2 w-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "0ms" }} />
            <div className="h-2 w-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "150ms" }} />
            <div className="h-2 w-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
          <span className="font-sans text-xs text-secondary font-medium animate-pulse">
            Synthesizing factual evidence...
          </span>
        </div>
      </div>
    );
  }

  // 3. Render Assistant Response
  const hasResponse = !!response;
  const preflightVerdict = response?.quality_gates?.preflight?.verdict;
  const isRefusal = preflightVerdict === "INSUFFICIENT";
  const sources = response?.sources || [];
  const displayAnswer = response?.answer || content;

  if (response?.mode === "multi_perspective") {
    return (
      <div className="w-full max-w-4xl mx-auto py-2">
        <CARAGResponse response={response} query={content} />
      </div>
    );
  }

  return (
    <div
      className={clsx(
        "flex flex-col gap-4 w-full max-w-4xl mx-auto px-6 py-5 border rounded-lg transition-all duration-base",
        isRefusal 
          ? "border-warning/50 bg-warning/5" 
          : "border-border bg-white shadow-sm"
      )}
      onClick={() => {
        // Highlight active sources in the right-side panel
        if (sources.length > 0) {
          setCurrentSources(sources);
        }
      }}
    >
      {/* Top Bar with Badges and Quality Gates status */}
      {hasResponse && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
          {/* Status Check indicators */}
          {response.quality_gates && response.latencies && (
            <GateStatusBar qualityGates={response.quality_gates} latencies={response.latencies} />
          )}

          {/* Confidence Badge */}
          <ConfidenceBadge confidence={response.confidence as ConfidenceLevel} />
        </div>
      )}

      {/* Answer Body Context */}
      <div className="font-sans">
        {isRefusal ? (
          <div className="flex items-start gap-3">
            <AlertTriangle className="text-warning shrink-0 mt-0.5" size={18} />
            <div className="flex-1">
              <span className="font-sans text-sm font-semibold text-warning block mb-1">
                Refusal Triggered: Insufficient Evidence
              </span>
              <p className="prose-answer font-sans text-base text-secondary italic">
                {displayAnswer}
              </p>
              {response?.quality_gates?.preflight?.gaps && response.quality_gates.preflight.gaps.length > 0 && (
                <div className="mt-2 bg-surface p-2.5 rounded border border-border">
                  <span className="font-sans text-xs font-semibold text-secondary block mb-1">Missing Parameters:</span>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {response.quality_gates.preflight.gaps.map((gap, i) => (
                      <li key={i} className="font-sans text-xs text-secondary">{gap}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ) : (response as any)?.mode === "multi_perspective" ? (
          <MultiPerspectiveAnswer response={response as any} query={content} />
        ) : (
          <div className="prose-answer">
            {parseCitations(displayAnswer, sources)}
          </div>
        )}
      </div>

      {/* Expandable Document Reference list */}
      {sources.length > 0 && (
        <div className="border-t border-border pt-3 mt-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsSourcesExpanded(!isSourcesExpanded);
            }}
            className="flex items-center gap-1.5 font-sans text-xs font-semibold text-secondary hover:text-accent transition-colors"
          >
            <BookOpen size={13} />
            <span>Document References ({sources.length})</span>
            {isSourcesExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>

          {isSourcesExpanded && (
            <ul className="mt-2 space-y-1.5 divide-y divide-border-strong/10">
              {sources.map((src, index) => (
                <li key={src.chunk_id} className="pt-1.5 first:pt-0">
                  <div className="flex items-center justify-between">
                    <span className="font-sans text-xs font-medium text-primary">
                      [{index + 1}] {src.metadata?.title || "Document Chunk"}
                    </span>
                    <span className="font-mono text-[10px] text-muted">
                      Score: {src.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="font-sans text-xs text-secondary line-clamp-1 mt-0.5">
                    {src.text}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Latency and timestamp details */}
      {response?.latencies && (
        <div className="flex items-center justify-end gap-3 text-[10px] text-muted border-t border-border/40 pt-2 select-none">
          <div className="flex items-center gap-1">
            <Clock size={10} />
            <span>Gen: {Math.round(response.latencies.generation_ms || 0)}ms</span>
          </div>
          <span>Total: {formatLatency(response.latencies.total_pipeline_ms || 0)}</span>
        </div>
      )}
    </div>
  );
}
