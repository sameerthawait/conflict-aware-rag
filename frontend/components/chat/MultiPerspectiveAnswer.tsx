"use client";
import React from "react";
import { MultiPerspectiveRAGResponse } from "@/lib/types";
import DisagreementMeter from "./DisagreementMeter";
import PerspectiveColumn from "./PerspectiveColumn";
import ContradictionHighlight from "./ContradictionHighlight";
import DisagreementExplanation from "./DisagreementExplanation";

interface MultiPerspectiveAnswerProps {
  response: MultiPerspectiveRAGResponse;
  query: string;
}

export default function MultiPerspectiveAnswer({ response, query }: MultiPerspectiveAnswerProps) {
  return (
    <div className="space-y-6">
      {/* 1. Synthesis/Balanced Answer */}
      <div className="bg-neutral-50 p-4 border border-neutral-200">
        <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-400 block mb-2">
          Synthesized Balanced Answer
        </span>
        <p className="font-sans text-base text-neutral-900 leading-relaxed">
          {response.answer}
        </p>
      </div>

      {/* 2. Disagreement Meter */}
      {response.disagreement_score && (
        <DisagreementMeter score={response.disagreement_score} />
      )}

      {/* 3. Side-by-Side Perspectives */}
      {response.perspectives && response.perspectives.length > 0 && (
        <div>
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500 block mb-3">
            Source Perspectives
          </span>
          <div className="flex flex-col md:flex-row gap-4 overflow-x-auto pb-2">
            {response.perspectives.map((cluster, idx) => (
              <PerspectiveColumn key={cluster.cluster_id} cluster={cluster} index={idx} />
            ))}
          </div>
        </div>
      )}

      {/* 4. Highlighted Contradictions */}
      {response.contradictions && response.contradictions.length > 0 && (
        <ContradictionHighlight contradictions={response.contradictions} />
      )}

      {/* 5. Explain Disagreement Interactive Widget */}
      {response.response_id && (
        <DisagreementExplanation query={query} responseId={response.response_id} />
      )}
    </div>
  );
}
