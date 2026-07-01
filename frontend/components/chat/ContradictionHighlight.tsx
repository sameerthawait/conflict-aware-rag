"use client";
import React from "react";
import { ContradictionResult } from "@/lib/types";
import { AlertTriangle, HelpCircle } from "lucide-react";

interface ContradictionHighlightProps {
  contradictions: ContradictionResult[];
}

export default function ContradictionHighlight({ contradictions }: ContradictionHighlightProps) {
  if (!contradictions || contradictions.length === 0) return null;

  return (
    <div className="border border-neutral-200 bg-white p-4 mb-6">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-neutral-100">
        <AlertTriangle size={18} className="text-red-600" />
        <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
          Detected Source Contradictions ({contradictions.length})
        </span>
      </div>

      <div className="space-y-4">
        {contradictions.map((c, idx) => (
          <div key={idx} className="border-l-2 border-red-600 pl-3 py-1 space-y-2">
            <div className="flex items-center gap-2 text-[10px] font-mono text-neutral-400">
              <span className="px-1.5 py-0.5 border border-red-600 text-red-600 uppercase font-bold text-[9px]">
                {c.contradiction_type || "Factual"}
              </span>
              <span>•</span>
              <span>Confidence: {(c.confidence * 100).toFixed(0)}%</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="bg-neutral-50 p-2 border border-neutral-100">
                <span className="font-mono text-[9px] uppercase tracking-wider text-neutral-400 block mb-1">Claim A</span>
                <p className="font-sans text-neutral-800">{c.claim_a}</p>
              </div>
              <div className="bg-neutral-50 p-2 border border-neutral-100">
                <span className="font-mono text-[9px] uppercase tracking-wider text-neutral-400 block mb-1">Claim B</span>
                <p className="font-sans text-neutral-800">{c.claim_b}</p>
              </div>
            </div>

            <p className="font-sans text-xs text-neutral-600 bg-red-50/30 p-2 border border-neutral-100">
              <strong className="font-mono text-[10px] uppercase text-neutral-500 block mb-0.5">Discrepancy Analysis:</strong>
              {c.explanation}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
