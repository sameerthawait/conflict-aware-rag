"use client";

import React, { useEffect, useState } from "react";
import { Zap, AlertTriangle, Info, Loader2 } from "lucide-react";
import clsx from "clsx";
import DisagreementMeter from "./DisagreementMeter";
import type { ConflictBannerProps } from "@/lib/types";

/**
 * Top alert banner displayed when source contradictions are detected.
 * Provides rapid feedback to researchers using WCAG-compliant alert roles.
 */
export default function ConflictBanner({
  disagreementScore,
  contradictionCount,
  clusterCount,
  onExplain,
  isExplainLoading = false,
  explanationText,
}: ConflictBannerProps) {
  const [mounted, setMounted] = useState(false);
  const [showMeter, setShowMeter] = useState(false);
  const [clickedExplain, setClickedExplain] = useState(false);

  // Mount animation trigger
  useEffect(() => {
    setMounted(true);
    const timer = setTimeout(() => setShowMeter(true), 300);
    return () => clearTimeout(timer);
  }, []);

  const handleExplainClick = () => {
    setClickedExplain(true);
    if (onExplain) {
      onExplain();
    }
  };

  const score = disagreementScore?.display_score || 0;

  // Visual classes based on disagreement score thresholds
  const getBannerStyles = (val: number) => {
    if (val <= 3) {
      return {
        bgClass: "bg-[#F59E0B]/5 border-[#F59E0B]/20 text-[#B45309]",
        icon: <Info size={16} className="shrink-0 text-[#B45309]" />,
      };
    } else if (val <= 6) {
      return {
        bgClass: "bg-[#F59E0B]/10 border-[#F59E0B]/30 text-[#D97706]",
        icon: <AlertTriangle size={16} className="shrink-0 text-[#D97706]" />,
      };
    } else {
      return {
        bgClass: "bg-danger/5 border-danger/20 text-danger",
        icon: <Zap size={16} className="shrink-0 text-danger" />,
      };
    }
  };

  const styles = getBannerStyles(score);

  return (
    <div
      role="alert"
      aria-live="polite"
      className={clsx(
        "w-full rounded-lg border p-4 select-none transition-all duration-300 transform",
        styles.bgClass,
        mounted ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0"
      )}
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        {/* Left column: Icon and conflict description */}
        <div className="flex items-start gap-3">
          <div className="mt-0.5">{styles.icon}</div>
          <div className="space-y-1">
            <h4 className="font-sans text-xs font-bold uppercase tracking-wider">
              Sources conflict on this topic
            </h4>
            <p className="font-sans text-xs leading-normal select-text opacity-95">
              Detected <span className="font-bold">{contradictionCount} contradictions</span> across{" "}
              <span className="font-bold">{clusterCount} distinct perspectives</span>.
            </p>
          </div>
        </div>

        {/* Right column: DisagreementMeter + explain button */}
        <div className="flex items-center gap-4 self-start sm:self-center shrink-0">
          <div className="w-[120px]">
            {showMeter ? (
              <DisagreementMeter
                score={score}
                interpretation=""
                size="sm"
                showLabel={false}
                showInterpretation={false}
                animated={true}
              />
            ) : (
              <div className="h-6 w-full bg-surface-2/20 animate-pulse rounded-md" />
            )}
          </div>

          {!clickedExplain && (
            <button
              onClick={handleExplainClick}
              disabled={isExplainLoading}
              className="inline-flex items-center gap-1.5 rounded border border-current px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide bg-transparent hover:bg-current/5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-offset-1 focus-visible:ring-accent transition-all duration-fast select-none shrink-0"
            >
              {isExplainLoading ? (
                <>
                  <Loader2 size={10} className="animate-spin" />
                  <span>Analyzing...</span>
                </>
              ) : (
                <span>Why do they conflict?</span>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Expanded explanation view */}
      {clickedExplain && (
        <div className="mt-3 border-t border-current/10 pt-3 text-xs leading-relaxed select-text font-sans">
          {isExplainLoading ? (
            <div className="flex items-center gap-2 py-1 select-none">
              <Loader2 size={12} className="animate-spin text-accent" />
              <span>Analyzing contradiction root causes...</span>
            </div>
          ) : (
            <div className="space-y-1">
              <span className="font-bold uppercase text-[10px] tracking-wider block opacity-75">
                Explanation Analysis
              </span>
              <p className="text-secondary select-text">
                {explanationText || disagreementScore?.interpretation || "No explanation text provided."}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Usage:
// <ConflictBanner
//   disagreementScore={disagreementScore}
//   contradictionCount={2}
//   clusterCount={3}
//   onExplain={fetchAnalysis}
//   isExplainLoading={loading}
//   explanationText="Standard medical sources advise 500mg daily, whereas clinical trials show..."
// />
