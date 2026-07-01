"use client";
import React from "react";
import { CostReport } from "@/lib/types";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from "recharts";
import { formatBytes } from "@/lib/utils/formatters";

interface CostChartProps {
  costs?: CostReport;
}

export default function CostChart({ costs }: CostChartProps) {
  // 1. Transform API Keys usage into charts dataset
  const chartData = React.useMemo(() => {
    if (!costs?.api_keys_usage) return [];
    
    return Object.entries(costs.api_keys_usage).map(([keyHash, stats]) => {
      // Shorten Key Hash for cleaner axis labels
      const label = keyHash.substring(0, 10) + "...";
      return {
        keyName: label,
        tier: stats.tier.toUpperCase(),
        "Tokens Used": stats.daily_tokens_used,
        "Daily Limit": stats.daily_token_limit,
        "Daily Cost ($)": parseFloat(stats.estimated_daily_cost_usd.toFixed(4)),
        "Pct Used": parseFloat(stats.daily_budget_pct.replace("%", ""))
      };
    });
  }, [costs]);

  const isEmpty = chartData.length === 0;

  return (
    <div className="rounded-lg border border-border bg-white p-5 shadow-sm select-none">
      <div className="border-b border-border/40 pb-3 mb-4 select-none">
        <h3 className="font-sans text-sm font-bold text-primary">Token Allocation & Usage</h3>
        <p className="font-sans text-xs text-secondary mt-0.5">
          Daily token utilization relative to designated authorization limits.
        </p>
      </div>

      <div className="h-72 w-full flex items-center justify-center">
        {isEmpty ? (
          <span className="font-sans text-xs text-muted">No key usage statistics loaded.</span>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 10, right: 10, left: 10, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
              <XAxis 
                dataKey="keyName" 
                tick={{ fill: "#4B5563", fontSize: 10, fontFamily: "var(--font-sans)" }} 
                stroke="#D1D5DB"
              />
              <YAxis 
                tick={{ fill: "#4B5563", fontSize: 10 }} 
                stroke="#D1D5DB"
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: "#FFFFFF", 
                  borderColor: "#E5E7EB",
                  fontFamily: "var(--font-sans)",
                  fontSize: "12px"
                }}
              />
              <Legend 
                wrapperStyle={{ 
                  fontSize: "11px",
                  fontFamily: "var(--font-sans)",
                  marginTop: "10px"
                }}
              />
              <Bar 
                dataKey="Tokens Used" 
                fill="#1A1A2E" 
                radius={[2, 2, 0, 0]} 
                maxBarSize={40}
              />
              <Bar 
                dataKey="Daily Limit" 
                fill="#EFF6FF" 
                stroke="#BFDBFE"
                radius={[2, 2, 0, 0]} 
                maxBarSize={40}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
