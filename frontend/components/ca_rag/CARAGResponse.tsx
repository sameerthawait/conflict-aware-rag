"use client";
import React, { useState } from "react";
import CARAGOverview from "./CARAGOverview";
import EvidenceView from "./EvidenceView";
import EvidenceTimeline from "./EvidenceTimeline";
import ConflictGraphView from "./ConflictGraphView";
import CitationExplorer from "./CitationExplorer";
import ConfidenceRadar from "./ConfidenceRadar";
import { AlertTriangle, Info, Clock, CheckCircle2, ShieldAlert } from "lucide-react";
import clsx from "clsx";

interface CARAGResponseProps {
  response: any;
  query: string;
}

export default function CARAGResponse({ response, query }: CARAGResponseProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "evidence" | "timeline" | "graph" | "citations">("overview");

  if (!response) return null;

  const {
    response_confidence,
    areas_of_disagreement = [],
    clusters = [],
    total_latency_ms,
    response_id
  } = response;

  const contradictionCount = areas_of_disagreement.length;
  const stanceCount = clusters.length;

  return (
    <div className="flex flex-col w-full max-w-5xl mx-auto bg-white border border-neutral-200 shadow-sm rounded-lg overflow-hidden selection:bg-neutral-900 selection:text-white">
      {/* 1. Conflict Warning & Statistics Banner */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 p-5 bg-neutral-50 border-b border-neutral-200">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded bg-neutral-950 text-white">
            <ShieldAlert size={20} className="animate-pulse" />
          </div>
          <div>
            <h3 className="font-mono text-sm font-bold text-neutral-900 uppercase tracking-wider">
              Conflict-Aware Evidence Synthesis
            </h3>
            <p className="font-sans text-xs text-neutral-500 mt-0.5">
              Detected contradictions within retrieving sources. Query: <span className="font-semibold text-neutral-800">"{query}"</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <span className="block font-mono text-[10px] font-bold text-neutral-400 uppercase">
              Contradiction Density
            </span>
            <span className="font-sans text-lg font-bold text-neutral-900">
              {(response_confidence.conflict_clarity * 100).toFixed(0)}%
            </span>
          </div>

          <div className="h-8 w-[1px] bg-neutral-200" />

          <div className="text-right">
            <span className="block font-mono text-[10px] font-bold text-neutral-400 uppercase">
              Stance Groups
            </span>
            <span className="font-sans text-lg font-semibold text-neutral-900">
              {stanceCount} Viewpoints
            </span>
          </div>

          <div className="h-8 w-[1px] bg-neutral-200" />

          <div className="text-right">
            <span className="block font-mono text-[10px] font-bold text-neutral-400 uppercase">
              Contradicted Claims
            </span>
            <span className="font-sans text-lg font-semibold text-red-600">
              {contradictionCount} Pairs
            </span>
          </div>
        </div>
      </div>

      {/* 2. Horizontal Navigation Tabs */}
      <div className="flex border-b border-neutral-200 bg-white overflow-x-auto select-none scrollbar-none">
        {(["overview", "evidence", "timeline", "graph", "citations"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={clsx(
              "px-6 py-3.5 font-mono text-xs font-bold uppercase tracking-wider border-b-2 transition-all duration-150 whitespace-nowrap focus:outline-none",
              activeTab === tab
                ? "border-neutral-950 text-neutral-950 bg-neutral-50/50"
                : "border-transparent text-neutral-400 hover:text-neutral-950 hover:bg-neutral-50/20"
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* 3. Main Coordinates Container Content */}
      <div className="p-6 min-h-[400px]">
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <CARAGOverview response={response} />
            </div>
            <div className="border-t lg:border-t-0 lg:border-l border-neutral-100 lg:pl-6">
              <ConfidenceRadar confidence={response_confidence} />
            </div>
          </div>
        )}

        {activeTab === "evidence" && (
          <EvidenceView response={response} query={query} />
        )}

        {activeTab === "timeline" && (
          <EvidenceTimeline clusters={clusters} />
        )}

        {activeTab === "graph" && (
          <ConflictGraphView response={response} />
        )}

        {activeTab === "citations" && (
          <CitationExplorer response={response} />
        )}
      </div>

      {/* 4. Mini Status Footer */}
      <div className="flex justify-between items-center px-6 py-3.5 bg-neutral-50 border-t border-neutral-200">
        <div className="flex items-center gap-2 text-[10px] font-mono text-neutral-400">
          <Clock size={12} />
          <span>LATENCY: {total_latency_ms}ms</span>
          <span className="text-neutral-300">|</span>
          <span>RESPONSE ID: {response_id}</span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] font-mono text-neutral-400">
          <CheckCircle2 size={12} className="text-neutral-500" />
          <span>AUTHENTICATED PREMIUM ACCESS</span>
        </div>
      </div>
    </div>
  );
}
