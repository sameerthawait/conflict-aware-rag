"use client";
import React from "react";
import { HealthStatus } from "@/lib/types";
import { 
  CheckCircle2, 
  AlertCircle, 
  XCircle, 
  HelpCircle,
  Database,
  Cpu,
  Layers,
  Zap,
  Activity
} from "lucide-react";
import clsx from "clsx";

interface HealthPanelProps {
  health?: HealthStatus;
}

export default function HealthPanel({ health }: HealthPanelProps) {
  // 1. Compile checks map
  const checks = health?.checks || {};
  const checksArray = Object.entries(checks);

  // Status mapping to icons and colors
  const getStatusIndicator = (statusStr: string) => {
    const status = (statusStr || "").toLowerCase();
    if (status === "healthy" || status === "active" || status === "closed" || status === "online") {
      return {
        icon: <CheckCircle2 className="text-success" size={15} />,
        colorText: "text-success",
        bgColor: "bg-success/5 border-success/20",
        label: "HEALTHY"
      };
    }
    if (status === "degraded" || status === "half-open" || status === "partial") {
      return {
        icon: <AlertCircle className="text-warning" size={15} />,
        colorText: "text-warning",
        bgColor: "bg-warning/5 border-warning/20",
        label: "DEGRADED"
      };
    }
    return {
      icon: <XCircle className="text-danger" size={15} />,
      colorText: "text-danger",
      bgColor: "bg-danger/5 border-danger/20",
      label: "OFFLINE"
    };
  };

  return (
    <div className="rounded-lg border border-border bg-white p-5 shadow-sm select-none">
      {/* Header */}
      <div className="border-b border-border/40 pb-3 mb-4 select-none">
        <h3 className="font-sans text-sm font-bold text-primary">Microservice Diagnostics</h3>
        <p className="font-sans text-xs text-secondary mt-0.5">
          Real-time ping checks and execution thresholds across components.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Module Health Check Status List */}
        <div>
          <span className="font-sans text-xs font-bold text-secondary uppercase tracking-wider block mb-3">
            Infrastructure Status Indicators
          </span>
          {checksArray.length === 0 ? (
            <div className="flex items-center justify-center p-8 border border-dashed border-border rounded bg-surface">
              <span className="font-sans text-xs text-muted">No diagnostic health probes reported.</span>
            </div>
          ) : (
            <div className="divide-y divide-border/40 border border-border rounded-md overflow-hidden bg-surface/20">
              {checksArray.map(([moduleName, status]) => {
                const diagnosis = getStatusIndicator(status);
                return (
                  <div key={moduleName} className="flex items-center justify-between px-4 py-3 bg-white hover:bg-surface/30 transition-colors">
                    <span className="font-sans text-xs font-semibold text-primary capitalize">
                      {moduleName.replace("_", " ")}
                    </span>
                    <div className={clsx("flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] font-bold select-none", diagnosis.bgColor, diagnosis.colorText)}>
                      {diagnosis.icon}
                      <span>{diagnosis.label}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Extended Stats (Queue, Cache, Circuit Breaker details) */}
        <div className="space-y-4">
          <span className="font-sans text-xs font-bold text-secondary uppercase tracking-wider block">
            Sub-System Configuration Parameters
          </span>

          <div className="rounded-md border border-border bg-white p-4 space-y-4 shadow-sm select-text">
            {/* Cache block */}
            {health?.cache && (
              <div className="flex items-start gap-3">
                <Zap size={16} className="text-accent shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-sans text-xs font-bold text-primary block leading-none">Semantic Query Cache</span>
                  <div className="grid grid-cols-3 gap-2 mt-2 bg-surface p-2 rounded border border-border text-center">
                    <div>
                      <span className="font-sans text-[9px] font-bold text-muted block leading-none">HITS</span>
                      <span className="font-mono text-xs font-bold text-primary block mt-1">{health.cache.hits}</span>
                    </div>
                    <div>
                      <span className="font-sans text-[9px] font-bold text-muted block leading-none">MISSES</span>
                      <span className="font-mono text-xs font-bold text-primary block mt-1">{health.cache.misses}</span>
                    </div>
                    <div>
                      <span className="font-sans text-[9px] font-bold text-muted block leading-none">HIT RATE</span>
                      <span className="font-mono text-xs font-bold text-primary block mt-1">{health.cache.hit_rate}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Queue block */}
            {health?.queue && (
              <div className="flex items-start gap-3 border-t border-border/40 pt-3">
                <Layers size={16} className="text-secondary shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-sans text-xs font-bold text-primary block leading-none">Concurrency Buffer</span>
                  <div className="grid grid-cols-3 gap-2 mt-2 bg-surface p-2 rounded border border-border text-center">
                    <div>
                      <span className="font-sans text-[9px] font-bold text-muted block leading-none">DEPTH</span>
                      <span className="font-mono text-xs font-bold text-primary block mt-1">{health.queue.depth}</span>
                    </div>
                    <div>
                      <span className="font-sans text-[9px] font-bold text-muted block leading-none">QUEUE LIMIT</span>
                      <span className="font-mono text-xs font-bold text-primary block mt-1">{health.queue.limit}</span>
                    </div>
                    <div>
                      <span className="font-sans text-[9px] font-bold text-muted block leading-none">WORKERS</span>
                      <span className="font-mono text-xs font-bold text-primary block mt-1">{health.queue.concurrency_limit}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Breaker block */}
            {health?.circuit_breaker && (
              <div className="flex items-start gap-3 border-t border-border/40 pt-3">
                <Activity size={16} className="text-success shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-sans text-xs font-bold text-primary block leading-none">Circuit Breaker System</span>
                  <div className="flex items-center justify-between mt-2 bg-surface px-3 py-2 rounded border border-border">
                    <span className="font-sans text-xs text-secondary font-medium">State Verdict:</span>
                    <span className={clsx("font-mono text-xs font-bold uppercase", getStatusIndicator(health.circuit_breaker.state).colorText)}>
                      {health.circuit_breaker.state}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
