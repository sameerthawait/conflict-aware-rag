"use client";
import React, { useState } from "react";
import { QualityGatesResponse } from "@/lib/types";
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  ChevronDown, 
  ChevronUp,
  Activity,
  AlertCircle
} from "lucide-react";
import clsx from "clsx";

interface GateStatusBarProps {
  qualityGates: QualityGatesResponse;
  latencies: Record<string, number>;
}

export default function GateStatusBar({ qualityGates, latencies }: GateStatusBarProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const { preflight, hallucination_verifier } = qualityGates;
  const totalLatency = latencies.total_pipeline_ms || 0;

  // 1. Preflight status settings
  const preflightVerdict = preflight.verdict;
  const isPreflightPassed = preflightVerdict === "SUFFICIENT" || preflightVerdict === "PARTIAL";
  const preflightColor = preflightVerdict === "SUFFICIENT" 
    ? "text-success border-success/30 bg-success/5"
    : preflightVerdict === "PARTIAL" 
      ? "text-warning border-warning/30 bg-warning/5"
      : "text-danger border-danger/30 bg-danger/5";

  // 2. Hallucination Verifier status settings
  const verifierVerdict = hallucination_verifier.verdict;
  const verifierColor = verifierVerdict === "PASS"
    ? "text-success border-success/30 bg-success/5"
    : verifierVerdict === "FAIL"
      ? "text-danger border-danger/30 bg-danger/5"
      : "text-muted border-border bg-surface";

  return (
    <div className="flex flex-col gap-2 select-none">
      {/* 1. Header Row of Compact Pills */}
      <div 
        onClick={(e) => {
          e.stopPropagation();
          setIsExpanded(!isExpanded);
        }}
        className="flex flex-wrap items-center gap-2 cursor-pointer hover:opacity-90"
      >
        {/* Preflight Pill */}
        <div className={clsx("flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold", preflightColor)}>
          {isPreflightPassed ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
          <span>Preflight: {preflightVerdict}</span>
        </div>

        {/* Verifier Pill */}
        {verifierVerdict && (
          <div className={clsx("flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold", verifierColor)}>
            {verifierVerdict === "PASS" ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
            <span>Verifier: {verifierVerdict}</span>
          </div>
        )}

        {/* Latency Pill */}
        <div className="flex items-center gap-1 rounded-full border border-border bg-surface text-secondary px-2 py-0.5 text-xs font-medium">
          <Clock size={11} />
          <span>{Math.round(totalLatency)}ms</span>
        </div>

        {/* Expand Trigger Icon */}
        <div className="text-muted group-hover:text-primary pl-1">
          {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </div>
      </div>

      {/* 2. Expanded Detail Card */}
      {isExpanded && (
        <div 
          onClick={(e) => e.stopPropagation()}
          className="mt-2 rounded-md border border-border bg-surface p-3 max-w-lg shadow-sm"
        >
          <div className="flex items-center gap-1.5 border-b border-border pb-1.5 mb-2">
            <Activity size={12} className="text-accent" />
            <span className="font-sans text-xs font-bold text-primary">System Quality Gates Audit</span>
          </div>

          <div className="space-y-3">
            {/* Preflight Logs */}
            <div>
              <span className="font-sans text-[11px] font-bold text-secondary block">Citation Preflight Gate:</span>
              <p className="font-sans text-xs text-secondary leading-relaxed mt-0.5">
                {preflight.reason || "Context chunks matched criteria successfully."}
              </p>
            </div>

            {/* Hallucination Verifier Logs */}
            {hallucination_verifier.audit && hallucination_verifier.audit.length > 0 && (
              <div>
                <span className="font-sans text-[11px] font-bold text-secondary block mb-1">
                  Anti-Hallucination Audit Checklist:
                </span>
                <ul className="space-y-1.5">
                  {hallucination_verifier.audit.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-2 bg-white p-2 rounded border border-border">
                      {item.supported ? (
                        <CheckCircle2 size={13} className="text-success shrink-0 mt-0.5" />
                      ) : (
                        <AlertCircle size={13} className="text-danger shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1 min-w-0">
                        <span className="font-sans text-[11px] font-medium text-primary block">
                          Claim: {item.claim}
                        </span>
                        {!item.supported && item.evidence && (
                          <span className="font-sans text-[10px] text-muted italic block mt-0.5">
                            Evidence gap: {item.evidence}
                          </span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
