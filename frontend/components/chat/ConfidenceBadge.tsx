"use client";
import React from "react";
import { ConfidenceLevel } from "@/lib/types";
import clsx from "clsx";

interface ConfidenceBadgeProps {
  confidence: ConfidenceLevel;
}

export default function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  // Determine text, color, and description tooltip
  let text = "Low Confidence";
  let classes = "bg-danger/10 text-danger border-danger/25";
  let tooltip = "Low Confidence: Response has low alignment scores or insufficient source documentation.";

  if (confidence === ConfidenceLevel.HIGH || String(confidence).toLowerCase() === "high") {
    text = "High Confidence";
    classes = "bg-success/10 text-success border-success/25";
    tooltip = "High Confidence: Factually verified answer fully grounded in the retrieved sources.";
  } else if (confidence === ConfidenceLevel.MEDIUM || String(confidence).toLowerCase() === "medium" || String(confidence).toLowerCase() === "partial") {
    text = "Partial Coverage";
    classes = "bg-warning/10 text-warning border-warning/25";
    tooltip = "Partial Coverage: Information satisfies major queries, but minor details are missing.";
  }

  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded border text-xs font-semibold select-none cursor-help transition-all duration-fast",
        classes
      )}
      title={tooltip}
    >
      {text}
    </span>
  );
}
