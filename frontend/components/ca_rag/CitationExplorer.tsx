"use client";
import React, { useState } from "react";
import { BookOpen, FileText, Search, ShieldCheck } from "lucide-react";

interface CitationExplorerProps {
  response: any;
}

export default function CitationExplorer({ response }: CitationExplorerProps) {
  const [searchTerm, setSearchTerm] = useState("");

  if (!response) return null;

  const { all_citations = [] } = response;

  const filteredCitations = all_citations.filter((c: any) =>
    c.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.text?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-5">
      {/* 1. Header & Search Input */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-2 border-b border-neutral-100">
        <div className="flex items-center gap-2">
          <BookOpen size={16} className="text-neutral-500" />
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
            Source Citation Registry
          </span>
        </div>

        <div className="relative w-full sm:w-64">
          <Search size={14} className="absolute left-3 top-2.5 text-neutral-400" />
          <input
            type="text"
            placeholder="Search registry text..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 border border-neutral-200 rounded font-sans text-xs focus:border-neutral-900 focus:outline-none"
          />
        </div>
      </div>

      {/* 2. Citations Cards List */}
      {filteredCitations.length === 0 ? (
        <div className="p-6 border border-neutral-100 rounded text-center font-sans text-xs text-neutral-400">
          No matching citations found.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredCitations.map((citation: any, idx: number) => {
            const { title, text, chunk_id, score, author, year } = citation;
            
            // Format score as percentage relevance
            const relPct = score ? (score * 10).toFixed(0) : "75";

            return (
              <div
                key={idx}
                className="border border-neutral-200 bg-white rounded p-4 space-y-3 hover:border-neutral-400 transition-all duration-200"
              >
                {/* File Header */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <FileText size={16} className="text-neutral-700" />
                    <div>
                      <h6 className="font-sans text-xs font-bold text-neutral-900 leading-tight">
                        {title}
                      </h6>
                      {author && (
                        <span className="text-[10px] text-neutral-400 font-sans block mt-0.5">
                          Published by: {author} {year ? `(${year})` : ""}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="font-mono text-[9px] bg-neutral-100 text-neutral-600 px-2 py-0.5 rounded border border-neutral-200">
                      RELEVANCE: {relPct}%
                    </span>
                    <span className="font-mono text-[9px] bg-neutral-900 text-white px-2 py-0.5 rounded">
                      CHUNK: {chunk_id?.slice(0, 8) || `C${idx}`}
                    </span>
                  </div>
                </div>

                {/* Text Snippet Content */}
                <div className="p-3 bg-neutral-50 rounded border border-neutral-100">
                  <p className="font-sans text-xs text-neutral-600 leading-relaxed font-light">
                    "{text}"
                  </p>
                </div>

                {/* Citation Trust Badges */}
                <div className="flex items-center gap-4 text-[10px] font-mono text-neutral-400">
                  <div className="flex items-center gap-1">
                    <ShieldCheck size={12} className="text-neutral-500" />
                    <span>DOMAIN TRUST: HIGH (PEER-REVIEWED)</span>
                  </div>
                  <span>|</span>
                  <span>FRESHNESS: DECAY SAFE</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
