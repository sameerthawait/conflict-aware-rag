"use client";
import React from "react";
import { CheckCircle2, ChevronRight, FileText } from "lucide-react";

interface CARAGOverviewProps {
  response: any;
}

export default function CARAGOverview({ response }: CARAGOverviewProps) {
  if (!response) return null;

  const {
    final_balanced_summary,
    supporting_evidence,
    contradicting_evidence,
    areas_of_agreement = []
  } = response;

  return (
    <div className="space-y-6">
      {/* 1. Final Balanced Summary */}
      <div className="space-y-2">
        <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-400">
          Synthesized Balanced Consensus
        </h4>
        <p className="font-sans text-base text-neutral-900 leading-relaxed font-light">
          {final_balanced_summary}
        </p>
      </div>

      <div className="h-[1px] bg-neutral-100" />

      {/* 2. Supporting Evidence */}
      <div className="space-y-2">
        <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-400">
          Supporting Evidence Breakdown
        </h4>
        <div className="p-4 bg-neutral-50/50 border border-neutral-100 rounded">
          <p className="font-sans text-sm text-neutral-700 leading-relaxed">
            {supporting_evidence}
          </p>
        </div>
      </div>

      <div className="h-[1px] bg-neutral-100" />

      {/* 3. Contradicting Evidence */}
      <div className="space-y-2">
        <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-400">
          Disagreement & Discrepancies Summary
        </h4>
        <div className="p-4 bg-red-50/20 border border-red-100/50 rounded">
          <p className="font-sans text-sm text-neutral-700 leading-relaxed">
            {contradicting_evidence}
          </p>
        </div>
      </div>

      {/* 4. Areas of Agreement list */}
      {areas_of_agreement.length > 0 && (
        <>
          <div className="h-[1px] bg-neutral-100" />
          <div className="space-y-3">
            <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-400">
              Areas of Consensus Agreement
            </h4>
            <ul className="space-y-2.5">
              {areas_of_agreement.map((item: string, idx: number) => (
                <li key={idx} className="flex items-start gap-2.5">
                  <span className="p-0.5 rounded-full bg-neutral-100 text-neutral-900 mt-0.5">
                    <CheckCircle2 size={13} />
                  </span>
                  <span className="font-sans text-sm text-neutral-700">
                    {item}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
