"use client";
import React, { useState } from "react";
import { RAGApiClient } from "@/lib/api";
import { useStore } from "@/lib/store";
import { AlertTriangle, Sparkles, Loader2, BookOpen, Compass, CheckCircle2 } from "lucide-react";
import clsx from "clsx";

interface ConflictPairCardProps {
  pair: any;
  responseId: string;
  query: string;
  index: number;
}

export default function ConflictPairCard({ pair, responseId, query, index }: ConflictPairCardProps) {
  const { apiKey } = useStore();
  const [explanation, setExplanation] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { claim_a, claim_b, contradiction_strength } = pair;

  const handleExplain = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const api = new RAGApiClient("/api/proxy", apiKey);
      const res = await api.explainConflict(responseId, claim_a.claim_id, claim_b.claim_id);
      setExplanation(res.explanation);
    } catch (err: any) {
      setError(err?.detail || err?.message || "Failed to fetch conflict explanation.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="border border-neutral-200 bg-white rounded overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 bg-neutral-50 border-b border-neutral-200 flex items-center justify-between">
        <span className="font-mono text-[10px] font-bold text-neutral-500 uppercase tracking-wider">
          Conflict Pair #{index + 1}
        </span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-neutral-400">Contradiction Strength:</span>
          <span className="font-mono text-xs font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded border border-red-100">
            {(contradiction_strength * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Side-by-Side Claims Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-neutral-200">
        {/* Claim A */}
        <div className="p-4 space-y-2 bg-neutral-50/20">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-neutral-400">
              Source A: {claim_a.source_title}
            </span>
            <span className="font-sans text-[9px] text-neutral-400">
              Conf: {(claim_a.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <p className="font-sans text-xs text-neutral-800 leading-relaxed font-medium">
            "{claim_a.claim_text}"
          </p>
        </div>

        {/* Claim B */}
        <div className="p-4 space-y-2 bg-neutral-50/20">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-neutral-400">
              Source B: {claim_b.source_title}
            </span>
            <span className="font-sans text-[9px] text-neutral-400">
              Conf: {(claim_b.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <p className="font-sans text-xs text-neutral-800 leading-relaxed font-medium">
            "{claim_b.claim_text}"
          </p>
        </div>
      </div>

      {/* Interactive Explanation Section */}
      <div className="p-4 border-t border-neutral-100 bg-white">
        {!explanation && !isLoading && (
          <button
            onClick={handleExplain}
            className="flex items-center gap-2 border border-neutral-900 bg-neutral-950 text-white font-mono text-[10px] font-bold uppercase tracking-wider px-4 py-2 rounded hover:bg-white hover:text-neutral-950 transition-all duration-150 shadow-sm"
          >
            <Sparkles size={12} />
            Generate Root Cause Explanation
          </button>
        )}

        {isLoading && (
          <div className="flex items-center gap-2.5 text-xs font-mono text-neutral-500 py-1">
            <Loader2 size={14} className="animate-spin text-neutral-800" />
            Analyzing semantic context, metadata freshness, and structural contradictions...
          </div>
        )}

        {error && (
          <div className="text-xs font-sans text-red-600 bg-red-50/50 p-2.5 rounded border border-red-100 flex items-start gap-2">
            <AlertTriangle size={14} className="mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {explanation && (
          <div className="space-y-4 font-sans text-xs leading-relaxed text-neutral-700 animate-fadeIn">
            {/* Primary Reason */}
            <div className="flex items-start gap-2 bg-neutral-50 p-3 rounded border border-neutral-100">
              <AlertTriangle size={14} className="text-neutral-900 mt-0.5 flex-shrink-0" />
              <div>
                <span className="font-mono text-[9px] font-bold uppercase block text-neutral-400">
                  Primary Cause
                </span>
                <span className="font-medium text-neutral-900">{explanation.primary_reason}</span>
              </div>
            </div>

            {/* Explanation Details */}
            <div className="space-y-1">
              <span className="font-mono text-[9px] font-bold uppercase text-neutral-400 block">
                Detailed Context
              </span>
              <p className="text-neutral-600 leading-relaxed font-light">
                {explanation.explanation}
              </p>
            </div>

            {/* Resolution Evidence */}
            <div className="flex items-start gap-2 p-3 bg-neutral-950 text-white rounded">
              <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0" />
              <div>
                <span className="font-mono text-[9px] font-bold uppercase tracking-wider block opacity-60">
                  Evidence-Backed Resolution
                </span>
                <p className="mt-0.5 font-light">{explanation.resolution_evidence}</p>
              </div>
            </div>

            {/* Practical Advice */}
            <div className="flex items-start gap-2 p-3 bg-neutral-50/50 border border-neutral-100 rounded">
              <Compass size={14} className="text-neutral-500 mt-0.5 flex-shrink-0" />
              <div>
                <span className="font-mono text-[9px] font-bold uppercase block text-neutral-400">
                  Practical Guidance
                </span>
                <p className="mt-0.5 text-neutral-600 font-light">{explanation.practical_advice}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
