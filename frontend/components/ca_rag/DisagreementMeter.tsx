"use client";

import React, { useEffect, useState } from "react";
import clsx from "clsx";
import type { DisagreementMeterProps } from "@/lib/types";

/**
 * Visual indicator representing the disagreement score (0-10) among sources.
 * Integrates ease-out cubic animation and supports WCAG contrast accessibility.
 */
export default function DisagreementMeter({
  score,
  interpretation,
  size = "md",
  showLabel = true,
  showInterpretation = true,
  animated = true,
  isLoading = false,
}: DisagreementMeterProps) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    if (isLoading) return;

    // Detect user motion preferences
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!animated || prefersReducedMotion) {
      setAnimatedScore(score);
      return;
    }

    let startTime: number | null = null;
    const duration = 800;

    const runAnimation = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // ease-out cubic easing
      const ease = 1 - Math.pow(1 - progress, 3);
      setAnimatedScore(ease * score);

      if (progress < 1) {
        requestAnimationFrame(runAnimation);
      }
    };

    const animFrame = requestAnimationFrame(runAnimation);
    return () => cancelAnimationFrame(animFrame);
  }, [score, animated, isLoading]);

  if (isLoading) {
    return (
      <div 
        role="presentation" 
        className={clsx(
          "animate-pulse bg-surface-2 rounded-md",
          size === "sm" && "h-6 w-[120px]",
          size === "md" && "h-12 w-[280px]",
          size === "lg" && "h-20 w-full"
        )}
      />
    );
  }

  // Visual thresholds config
  const getStatusDetails = (val: number) => {
    if (val <= 3) {
      return {
        colorClass: "bg-success border-success/40 text-success",
        label: "Sources broadly agree",
      };
    } else if (val <= 6) {
      return {
        colorClass: "bg-warning border-warning/40 text-warning",
        label: "Meaningful disagreement",
      };
    } else {
      return {
        colorClass: "bg-danger border-danger/40 text-danger",
        label: "Strong contradiction",
      };
    }
  };

  const currentScore = Math.max(0, Math.min(score, 10));
  const fillPct = (animatedScore / 10) * 100;
  const status = getStatusDetails(currentScore);
  const isMaxContradiction = currentScore === 10;

  return (
    <div 
      className={clsx(
        "flex flex-col select-none",
        size === "sm" && "w-[120px]",
        size === "md" && "w-[280px]",
        size === "lg" && "w-full"
      )}
    >
      <div className="flex items-center gap-3">
        {/* Horizontal Meter Bar Wrapper */}
        <div className="relative flex-1">
          {/* Progress bar background tracks */}
          <div className="relative h-2 w-full rounded-full bg-surface-2 overflow-hidden border border-border">
            <div 
              role="meter"
              aria-valuenow={currentScore}
              aria-valuemin={0}
              aria-valuemax={10}
              aria-label={`Disagreement score: ${currentScore} out of 10. ${status.label}`}
              className={clsx(
                "h-full rounded-full transition-all duration-75",
                currentScore <= 3 && "bg-success",
                currentScore > 3 && currentScore <= 6 && "bg-warning",
                currentScore > 6 && "bg-danger"
              )}
              style={{ width: `${fillPct}%` }}
            />
          </div>

          {/* Value Needle Indicator */}
          <div 
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 transition-all duration-75"
            style={{ left: `${fillPct}%` }}
          >
            <div 
              className={clsx(
                "h-4 w-1.5 rounded-full shadow-sm border border-white",
                currentScore <= 3 && "bg-success",
                currentScore > 3 && currentScore <= 6 && "bg-warning",
                currentScore > 6 && "bg-danger",
                isMaxContradiction && "animate-ping"
              )}
            />
          </div>
        </div>

        {/* Bold Score Text readout */}
        <span className="font-mono text-xl font-bold text-primary shrink-0 select-text">
          {currentScore.toFixed(1)}
        </span>
      </div>

      {/* Label and Interpretation readout below */}
      {showLabel && size !== "sm" && (
        <div className="flex items-center justify-between mt-1.5 text-[10px] font-bold text-secondary tracking-wide uppercase">
          <span>{status.label}</span>
        </div>
      )}

      {showInterpretation && size === "lg" && interpretation && (
        <p className="mt-2 font-sans text-xs text-secondary leading-relaxed select-text border-t border-border/40 pt-2">
          <span className="font-bold">Interpretation: </span>
          {interpretation}
        </p>
      )}
    </div>
  );
}

// Usage:
// <DisagreementMeter
//   score={7.5}
//   interpretation="Sources disagree on standard dosages."
//   size="lg"
// />
