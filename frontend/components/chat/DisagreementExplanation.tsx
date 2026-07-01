"use client";
import React, { useState } from "react";
import { RAGApiClient } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Sparkles, HelpCircle, Loader2 } from "lucide-react";

interface DisagreementExplanationProps {
  query: string;
  responseId: string;
}

export default function DisagreementExplanation({ query, responseId }: DisagreementExplanationProps) {
  const { apiKey } = useStore();
  const [explanation, setExplanation] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<number | null>(null);

  const handleExplain = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const api = new RAGApiClient("/api/proxy", apiKey);
      const data = await api.explainDisagreement(query, responseId);
      setExplanation(data.explanation);
      setLatency(data.latency_ms);
    } catch (err: any) {
      setError(err?.detail || err?.message || "Failed to generate explanation.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="border border-neutral-200 bg-white p-4 mb-6">
      <div className="flex items-center justify-between pb-2 border-b border-neutral-100 mb-3">
        <div className="flex items-center gap-2">
          <HelpCircle size={18} className="text-neutral-900" />
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
            Synthesized Explanation of Discrepancies
          </span>
        </div>
        {latency !== null && (
          <span className="font-mono text-[10px] text-neutral-400">
            Analyzed in {latency}ms
          </span>
        )}
      </div>

      {!explanation && !isLoading && (
        <button
          onClick={handleExplain}
          className="flex items-center gap-2 border border-neutral-900 bg-neutral-900 text-white text-xs font-mono uppercase tracking-wider px-4 py-2 hover:bg-white hover:text-neutral-900 transition-colors"
        >
          <Sparkles size={14} />
          Explain Disagreement
        </button>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-xs font-mono text-neutral-500 py-2">
          <Loader2 size={16} className="animate-spin" />
          Reconstructing debate context and synthesizing stance resolutions...
        </div>
      )}

      {error && (
        <div className="text-xs font-sans text-red-600 bg-red-50 p-2 border border-red-100">
          {error}
        </div>
      )}

      {explanation && (
        <div className="prose prose-sm max-w-none text-neutral-800 font-sans text-sm leading-relaxed space-y-2">
          {explanation.split("\n\n").map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </div>
      )}
    </div>
  );
}
