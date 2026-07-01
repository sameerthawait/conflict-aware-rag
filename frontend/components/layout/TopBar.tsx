"use client";
import React from "react";
import { usePathname } from "next/navigation";
import { useStore } from "@/lib/store";
import { useAdmin } from "@/lib/hooks/useAdmin";
import { Trash2, Columns, RefreshCw } from "lucide-react";
import clsx from "clsx";

interface TopBarProps {
  title: string;
  onToggleSources?: () => void;
  isSourcesOpen?: boolean;
}

export default function TopBar({ title, onToggleSources, isSourcesOpen }: TopBarProps) {
  const pathname = usePathname();
  const { clearChat, messages } = useStore();
  const { health, isHealthLoading, refetchHealth } = useAdmin();

  // Get latency of last message response
  const lastMessage = messages[messages.length - 1];
  const lastLatency = lastMessage?.response?.latencies?.total_pipeline_ms;

  const isChatPage = pathname === "/chat";

  // Determine health color
  const healthStatus = health?.status || "offline";
  const healthColorMap = {
    healthy: "bg-success",
    degraded: "bg-warning",
    offline: "bg-danger"
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-white px-6">
      {/* 1. Left - Page Title */}
      <h1 className="font-sans text-base font-semibold text-primary">
        {title}
      </h1>

      {/* 2. Right - Controls, Metrics, and Status Indicators */}
      <div className="flex items-center gap-4">
        {/* Latency Indicator (Displays only when there is a valid query latency) */}
        {isChatPage && lastLatency !== undefined && (
          <span className="font-sans text-xs text-muted">
            Latency: {Math.round(lastLatency)}ms
          </span>
        )}

        {/* Health Check indicator dot */}
        <div className="flex items-center gap-2 border-r border-border pr-4">
          <button
            onClick={() => refetchHealth()}
            disabled={isHealthLoading}
            className="rounded p-1 text-secondary hover:bg-surface-2 disabled:opacity-50 transition-colors"
            title="Refresh System Health"
          >
            <RefreshCw size={12} className={clsx(isHealthLoading && "animate-spin")} />
          </button>
          <div
            className={clsx(
              "h-2.5 w-2.5 rounded-full",
              healthColorMap[healthStatus] || "bg-danger"
            )}
            title={`System Status: ${healthStatus.toUpperCase()}`}
          />
          <span className="font-sans text-xs text-secondary hidden sm:inline select-none">
            {healthStatus === "healthy" ? "System Active" : `System: ${healthStatus}`}
          </span>
        </div>

        {/* Clear Chat Button (Chat page only) */}
        {isChatPage && messages.length > 0 && (
          <button
            onClick={clearChat}
            className="flex items-center gap-1.5 rounded border border-border bg-white px-2.5 py-1 font-sans text-xs font-medium text-secondary hover:bg-surface-2 hover:text-primary transition-all duration-fast"
          >
            <Trash2 size={12} />
            <span>Clear History</span>
          </button>
        )}

        {/* Collapsible Citations Toggle (Chat page only, when sources exist) */}
        {onToggleSources && (
          <button
            onClick={onToggleSources}
            className={clsx(
              "flex items-center gap-1.5 rounded border px-2.5 py-1 font-sans text-xs font-medium transition-all duration-fast",
              isSourcesOpen
                ? "bg-accent border-accent text-white hover:bg-accent-hover"
                : "bg-white border-border text-secondary hover:bg-surface-2 hover:text-primary"
            )}
            title={isSourcesOpen ? "Hide Citations Panel" : "Show Citations Panel"}
          >
            <Columns size={12} />
            <span className="hidden sm:inline">Citations</span>
          </button>
        )}
      </div>
    </header>
  );
}
