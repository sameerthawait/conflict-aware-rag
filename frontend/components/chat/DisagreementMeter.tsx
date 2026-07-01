"use client";
import React from "react";
import { DisagreementScore } from "@/lib/types";
import { AlertCircle, Scale } from "lucide-react";

interface DisagreementMeterProps {
  score: DisagreementScore;
}

export default function DisagreementMeter({ score }: DisagreementMeterProps) {
  const percentage = (score.display_score / 10) * 100;
  
  // High contrast clinical color coding
  let levelColor = "bg-neutral-900";
  let textColor = "text-neutral-900";
  let borderColor = "border-neutral-900";
  
  if (score.display_score >= 7) {
    levelColor = "bg-red-600";
    textColor = "text-red-600";
    borderColor = "border-red-600";
  } else if (score.display_score >= 4) {
    levelColor = "bg-amber-600";
    textColor = "text-amber-600";
    borderColor = "border-amber-600";
  }

  return (
    <div className={`p-4 border ${borderColor} bg-white rounded-none mb-6`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Scale size={18} className={textColor} />
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
            Source Disagreement Index
          </span>
        </div>
        <div className="flex items-baseline gap-1">
          <span className="font-mono text-2xl font-bold tracking-tight">{score.display_score}</span>
          <span className="font-mono text-xs text-neutral-400">/10</span>
        </div>
      </div>
      
      {/* Progress bar container */}
      <div className="h-2 w-full bg-neutral-100 mb-3 rounded-none overflow-hidden border border-neutral-200">
        <div 
          className={`h-full ${levelColor} transition-all duration-500`} 
          style={{ width: `${percentage}%` }}
        />
      </div>

      <div className="space-y-1">
        <div className="flex items-center gap-1.5">
          {score.display_score >= 4 && <AlertCircle size={14} className={textColor} />}
          <span className="font-sans text-sm font-semibold text-neutral-900">
            {score.interpretation}
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2 pt-2 border-t border-neutral-100 font-mono text-xs text-neutral-500">
          <div>
            <span className="font-semibold text-neutral-700">Dominant Perspective:</span> {score.dominant_perspective}
          </div>
          {score.minority_perspective && (
            <div>
              <span className="font-semibold text-neutral-700">Contrasting Stance:</span> {score.minority_perspective}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
