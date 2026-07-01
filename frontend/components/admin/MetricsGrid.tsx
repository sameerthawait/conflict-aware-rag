"use client";
import React from "react";
import { HealthStatus, CostReport } from "@/lib/types";
import { 
  Zap, 
  Coins, 
  Layers, 
  Activity, 
  Cpu 
} from "lucide-react";

interface MetricsGridProps {
  health?: HealthStatus;
  costs?: CostReport;
}

export default function MetricsGrid({ health, costs }: MetricsGridProps) {
  // 1. Calculate Token Spending
  let totalDailyCost = 0;
  let totalDailyTokens = 0;
  let totalMonthlyCost = 0;
  let activeKeysCount = 0;

  if (costs?.api_keys_usage) {
    const usages = Object.values(costs.api_keys_usage);
    activeKeysCount = usages.length;
    usages.forEach((usage) => {
      totalDailyCost += usage.estimated_daily_cost_usd || 0;
      totalDailyTokens += usage.daily_tokens_used || 0;
      totalMonthlyCost += usage.estimated_monthly_cost_usd || 0;
    });
  }

  // 2. Fetch Cache Stats
  const cacheHitRate = health?.cache?.hit_rate || "0.0%";
  const cacheEntries = health?.cache?.active_entries_count || 0;

  // 3. Fetch Concurrency details
  const queueDepth = health?.queue?.depth ?? 0;
  const queueLimit = health?.queue?.limit ?? 50;

  // 4. Circuit Breaker state
  const cbState = health?.circuit_breaker?.state || "CLOSED";

  const metrics = [
    {
      title: "Daily Spend Estimate",
      value: `$${totalDailyCost.toFixed(4)}`,
      subText: `Est. Monthly: $${totalMonthlyCost.toFixed(2)}`,
      icon: <Coins size={16} className="text-success" />,
      desc: `Aggregated spending across ${activeKeysCount} active key tiers`
    },
    {
      title: "Cache Efficiency",
      value: cacheHitRate,
      subText: `${cacheEntries} active cached statements`,
      icon: <Zap size={16} className="text-accent" />,
      desc: "Percentage of queries resolved via semantic search cache"
    },
    {
      title: "Queue Load Depth",
      value: `${queueDepth} / ${queueLimit}`,
      subText: `Concurrency cap: ${health?.queue?.concurrency_limit || 5}`,
      icon: <Layers size={16} className="text-secondary" />,
      desc: "Incoming requests currently waiting inside execution buffers"
    },
    {
      title: "NVIDIA NIM Circuit Breaker",
      value: cbState,
      subText: cbState === "CLOSED" ? "All models operational" : `Fails: ${health?.circuit_breaker?.consecutive_failures || 0}`,
      icon: <Activity size={16} className={cbState === "CLOSED" ? "text-success" : "text-danger"} />,
      desc: "Automated fail-safe gateway monitoring model timeouts"
    }
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 select-none">
      {metrics.map((item, i) => (
        <div 
          key={i} 
          className="rounded-lg border border-border bg-white p-4.5 shadow-sm hover:shadow transition-shadow select-none"
        >
          <div className="flex items-center justify-between border-b border-border/40 pb-2 mb-2 select-none">
            <span className="font-sans text-xs font-bold text-secondary uppercase tracking-wider">
              {item.title}
            </span>
            <div className="bg-surface-2 p-1.5 rounded border border-border shrink-0">
              {item.icon}
            </div>
          </div>

          <div className="flex flex-col select-text">
            <span className="font-mono text-2xl font-bold text-primary">
              {item.value}
            </span>
            <span className="font-sans text-[11px] font-semibold text-secondary block mt-0.5">
              {item.subText}
            </span>
          </div>

          <p className="font-sans text-[10px] text-muted leading-relaxed mt-2 select-none border-t border-border/40 pt-2">
            {item.desc}
          </p>
        </div>
      ))}
    </div>
  );
}
