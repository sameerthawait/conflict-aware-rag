"use client";
import React, { useState } from "react";
import ConflictPairCard from "./ConflictPairCard";
import { AlertCircle, Layers, Split, Info, HelpCircle } from "lucide-react";
import clsx from "clsx";

interface EvidenceViewProps {
  response: any;
  query: string;
}

export default function EvidenceView({ response, query }: EvidenceViewProps) {
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);

  if (!response) return null;

  const {
    clusters = [],
    areas_of_disagreement = [],
    response_id
  } = response;

  return (
    <div className="space-y-8">
      {/* 1. Stance Clusters Grid */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Layers size={16} className="text-neutral-500" />
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
            Factual Stance Clusters
          </span>
          <span className="text-[10px] font-sans text-neutral-400 bg-neutral-100 px-2 py-0.5 rounded">
            Spectral Clustering
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {clusters.map((cluster: any, idx: number) => {
            const isRepresentativeHighlighted = selectedClaimId === cluster.representative_claim?.claim_id;

            return (
              <div
                key={cluster.cluster_id}
                className="flex flex-col border border-neutral-200 rounded overflow-hidden hover:border-neutral-400 transition-all duration-200"
              >
                {/* Cluster Header */}
                <div className="px-4 py-3 bg-neutral-50 border-b border-neutral-200 flex items-center justify-between">
                  <div>
                    <span className="block font-mono text-[10px] font-bold text-neutral-400 uppercase">
                      Stance {idx + 1}
                    </span>
                    <h5 className="font-sans text-xs font-bold text-neutral-900 mt-0.5">
                      {cluster.label}
                    </h5>
                  </div>
                  <span className="font-sans text-[10px] bg-neutral-900 text-white font-medium px-2 py-0.5 rounded">
                    {(cluster.confidence * 100).toFixed(0)}% Conf.
                  </span>
                </div>

                {/* Stance Claims List */}
                <div className="p-4 flex-1 space-y-3 bg-white">
                  {cluster.claims.map((claim: any) => {
                    const isSelected = selectedClaimId === claim.claim_id;

                    return (
                      <div
                        key={claim.claim_id}
                        onClick={() => setSelectedClaimId(isSelected ? null : claim.claim_id)}
                        className={clsx(
                          "p-3 rounded border text-xs leading-relaxed cursor-pointer transition-all duration-150",
                          isSelected
                            ? "bg-neutral-900 text-white border-neutral-900 shadow-sm"
                            : "bg-neutral-50 hover:bg-neutral-100 text-neutral-700 border-neutral-100"
                        )}
                      >
                        <span className="block font-mono text-[9px] uppercase tracking-wider opacity-60 mb-1">
                          {claim.source_title}
                        </span>
                        <p>{claim.claim_text}</p>
                      </div>
                    );
                  })}
                </div>

                {/* Representative Claim Footer */}
                {cluster.representative_claim && (
                  <div className="px-4 py-2.5 bg-neutral-50/50 border-t border-neutral-100 text-[10px] text-neutral-500">
                    <span className="font-semibold text-neutral-700">REP:</span>{" "}
                    {cluster.representative_claim.claim_text.slice(0, 70)}...
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="h-[1px] bg-neutral-100" />

      {/* 2. Detected Contradictions Section */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Split size={16} className="text-neutral-500" />
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
            Contradictory Claim Pairs
          </span>
          <span className="text-[10px] font-sans text-neutral-400 bg-neutral-100 px-2 py-0.5 rounded">
            NLI Classification
          </span>
        </div>

        {areas_of_disagreement.length === 0 ? (
          <div className="p-5 border border-neutral-100 rounded text-center text-xs text-neutral-400">
            No contradictory claim pairs detected.
          </div>
        ) : (
          <div className="space-y-4">
            {areas_of_disagreement.map((pair: any, idx: number) => (
              <ConflictPairCard
                key={idx}
                pair={pair}
                responseId={response_id}
                query={query}
                index={idx}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
