"use client";
import React from "react";
import { PerspectiveCluster } from "@/lib/types";
import { ShieldCheck, MessageSquare, Award } from "lucide-react";

interface PerspectiveColumnProps {
  cluster: PerspectiveCluster;
  index: number;
}

export default function PerspectiveColumn({ cluster, index }: PerspectiveColumnProps) {
  return (
    <div className="flex-1 min-w-[280px] bg-white border border-neutral-200 p-4 flex flex-col justify-between transition-all hover:border-neutral-400">
      <div>
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-neutral-100">
          <div className="flex items-center gap-2">
            <span className="flex items-center justify-center w-5 h-5 rounded-none bg-neutral-900 text-white font-mono text-xs font-bold">
              {index + 1}
            </span>
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
              Perspective
            </span>
          </div>
          <div className="flex items-center gap-1 font-mono text-[10px] text-neutral-400">
            <span>Avg Confidence:</span>
            <span className="font-bold text-neutral-700">{(cluster.avg_confidence * 100).toFixed(0)}%</span>
          </div>
        </div>

        <h4 className="font-sans text-base font-bold text-neutral-950 mb-3 leading-snug">
          {cluster.label}
        </h4>

        <div className="space-y-4">
          {cluster.perspectives.map((p, idx) => (
            <div key={idx} className="bg-neutral-50 p-3 border border-neutral-100 space-y-2">
              <div className="flex items-center justify-between text-[11px] font-mono text-neutral-400">
                <span className="font-semibold text-neutral-700 max-w-[150px] truncate" title={p.source}>
                  Source: {p.source}
                </span>
                <span className={`px-1 py-0.5 border ${
                  p.source_confidence === "high" 
                    ? "border-neutral-900 text-neutral-900 font-bold" 
                    : "border-neutral-200 text-neutral-500"
                } uppercase tracking-wider text-[9px]`}>
                  {p.source_confidence} Trust
                </span>
              </div>

              <div className="font-sans text-xs text-neutral-800 leading-relaxed italic">
                "{p.position}"
              </div>

              {p.key_evidence && (
                <div className="text-[11px] text-neutral-600 font-sans pl-2 border-l border-neutral-300">
                  <strong className="text-[10px] uppercase font-mono tracking-wider block text-neutral-400">Evidence:</strong>
                  {p.key_evidence}
                </div>
              )}

              {p.caveats && (
                <div className="text-[11px] text-neutral-500 font-sans italic">
                  <strong className="text-[10px] uppercase font-mono tracking-wider not-italic block text-neutral-400">Caveat:</strong>
                  {p.caveats}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      
      <div className="mt-4 pt-2 border-t border-neutral-100 flex items-center justify-between font-mono text-[10px] text-neutral-400">
        <span>Supporting Chunks:</span>
        <span className="font-bold text-neutral-700">{cluster.chunk_count}</span>
      </div>
    </div>
  );
}
