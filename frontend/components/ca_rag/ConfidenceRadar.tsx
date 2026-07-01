"use client";

import React from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from "recharts";
import clsx from "clsx";
import type { ConfidenceRadarProps } from "@/lib/types";

/**
 * Radar chart mapping confidence scores across 5 dimensions:
 * Relevance, Quality, Citations, Freshness, and Contradiction Strength.
 */
export default function ConfidenceRadar({
  supportingCluster,
  contradictingCluster,
  confidence,
  size = 280,
  showLegend = true,
  showValues = true,
  isLoading = false,
}: ConfidenceRadarProps) {
  if (isLoading) {
    return (
      <div 
        role="presentation"
        className="flex items-center justify-center border border-dashed border-border rounded-full animate-pulse mx-auto bg-surface"
        style={{ width: size, height: size }}
      >
        <span className="font-sans text-[10px] font-bold text-muted uppercase tracking-wider">
          Loading Radar...
        </span>
      </div>
    );
  }

  const finalSupporting = supportingCluster || (confidence ? {
    relevance: confidence.overall,
    quality: confidence.dominant_cluster_confidence,
    citations: confidence.minority_cluster_confidence,
    freshness: confidence.conflict_clarity,
    contradiction: 1 - confidence.conflict_clarity
  } : {
    relevance: 0,
    quality: 0,
    citations: 0,
    freshness: 0,
    contradiction: 0
  });

  const finalContradicting = contradictingCluster;

  // Map 5 axis dimensions. Contradiction Strength is inverted (higher = less contradiction)
  const data = [
    {
      subject: "Relevance",
      Supporting: finalSupporting.relevance,
      ...(finalContradicting ? { Contradicting: finalContradicting.relevance } : {}),
      fullMark: 1.0,
    },
    {
      subject: "Quality",
      Supporting: finalSupporting.quality,
      ...(finalContradicting ? { Contradicting: finalContradicting.quality } : {}),
      fullMark: 1.0,
    },
    {
      subject: "Citations",
      Supporting: finalSupporting.citations,
      ...(finalContradicting ? { Contradicting: finalContradicting.citations } : {}),
      fullMark: 1.0,
    },
    {
      subject: "Freshness",
      Supporting: finalSupporting.freshness,
      ...(finalContradicting ? { Contradicting: finalContradicting.freshness } : {}),
      fullMark: 1.0,
    },
    {
      subject: "Consensus",
      Supporting: finalSupporting.contradiction,
      ...(finalContradicting ? { Contradicting: finalContradicting.contradiction } : {}),
      fullMark: 1.0,
    },
  ];

  return (
    <div 
      className="flex flex-col items-center justify-center mx-auto select-none"
      style={{ width: "100%", height: size + 40 }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="#E5E7EB" />
          <PolarAngleAxis 
            dataKey="subject" 
            tick={{ fill: "#4B5563", fontSize: 9, fontWeight: 600 }}
          />
          <PolarRadiusAxis 
            angle={30} 
            domain={[0, 1.0]} 
            tick={{ fill: "#9CA3AF", fontSize: 8 }}
          />
          
          <Tooltip 
            contentStyle={{
              fontSize: "10px",
              fontFamily: "var(--font-sans)",
              borderRadius: "6px",
              border: "1px border-border",
              background: "#1A1A2E",
              color: "#FFF",
            }}
          />

          {/* Supporting Perspective: Green Radar Fill */}
          <Radar
            name="Supporting"
            dataKey="Supporting"
            stroke="#059669"
            fill="#059669"
            fillOpacity={0.25}
          />

          {/* Contradicting Perspective: Red Radar Fill (Optional) */}
          {contradictingCluster && (
            <Radar
              name="Contradicting"
              dataKey="Contradicting"
              stroke="#DC2626"
              fill="#DC2626"
              fillOpacity={0.25}
            />
          )}

          {showLegend && contradictingCluster && (
            <Legend 
              wrapperStyle={{ fontSize: "10px", fontWeight: 600 }}
            />
          )}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Usage:
// <ConfidenceRadar
//   supportingCluster={{ relevance: 0.9, quality: 0.8, citations: 0.6, freshness: 0.7, contradiction: 0.9 }}
//   contradictingCluster={{ relevance: 0.7, quality: 0.9, citations: 0.4, freshness: 0.5, contradiction: 0.4 }}
//   size={280}
// />
