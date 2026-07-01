"use client";
import React, { useState } from "react";
import Layout from "@/components/layout/Layout";
import { useStore } from "@/lib/store";
import { useAdmin } from "@/lib/hooks/useAdmin";
import MetricsGrid from "@/components/admin/MetricsGrid";
import CostChart from "@/components/admin/CostChart";
import GateVerdictChart from "@/components/admin/GateVerdictChart";
import HealthPanel from "@/components/admin/HealthPanel";
import MultiPerspectivePanel from "@/components/admin/MultiPerspectivePanel";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import { Key, ShieldCheck, RefreshCw, AlertTriangle } from "lucide-react";
import clsx from "clsx";

export default function AdminPage() {
  const { apiKey, setApiKey } = useStore();
  const { health, costs, isHealthLoading, isCostsLoading, refetchHealth, refetchCosts } = useAdmin();
  const [keyValue, setKeyValue] = useState(apiKey);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [mounted, setMounted] = useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (mounted) {
      setKeyValue(apiKey);
    }
  }, [apiKey, mounted]);

  const handleSaveKey = (e: React.FormEvent) => {
    e.preventDefault();
    setApiKey(keyValue);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2500);
  };

  const handleRefreshAll = () => {
    refetchHealth();
    refetchCosts();
  };

  const isKeyMissing = mounted ? !apiKey : true;

  return (
    <Layout title="System Administration">
      <div className="max-w-6xl mx-auto space-y-8 select-none">
        
        {/* Top Control Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4 select-none">
          <div>
            <h2 className="font-sans text-sm font-bold text-primary">System Monitoring Dashboard</h2>
            <p className="font-sans text-xs text-secondary mt-0.5">
              Review token economics, request pipeline diagnostics, and microservice status logs.
            </p>
          </div>
          <button
            onClick={handleRefreshAll}
            disabled={isHealthLoading || isCostsLoading}
            className="flex items-center gap-1.5 rounded border border-border bg-white px-3 py-1.5 font-sans text-xs font-semibold text-secondary hover:bg-surface-2 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={13} className={clsx((isHealthLoading || isCostsLoading) && "animate-spin")} />
            <span>Sync Stats</span>
          </button>
        </div>

        {/* 1. API Authorization Key Config Panel */}
        <div className="rounded-lg border border-border bg-white p-5 shadow-sm">
          <h2 className="font-sans text-sm font-bold text-primary flex items-center gap-2 mb-2">
            <Key size={16} className="text-accent" />
            <span>API Gateway Access Control</span>
          </h2>
          <p className="font-sans text-xs text-secondary leading-relaxed mb-4">
            Operations inside the RAG system require backend authorization. Set your secret API key below to authorize requests.
          </p>

          <form onSubmit={handleSaveKey} className="flex flex-col sm:flex-row gap-3 max-w-2xl">
            <div className="flex-1">
              <Input
                type="password"
                placeholder="Enter authorized X-API-Key..."
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
            <div className="shrink-0 flex items-end">
              <Button type="submit" variant="primary" className="w-full sm:w-auto h-[38px]">
                Save Key Reference
              </Button>
            </div>
          </form>

          {saveSuccess && (
            <span className="flex items-center gap-1 mt-2 text-xs font-bold text-success">
              <ShieldCheck size={14} />
              <span>Key saved to local browser context. Header inject active.</span>
            </span>
          )}
        </div>

        {/* Informative Banner when key is missing */}
        {isKeyMissing && (
          <div className="flex items-start gap-3 rounded-lg border border-warning/35 bg-warning/5 p-4 text-warning">
            <AlertTriangle className="shrink-0 mt-0.5" size={18} />
            <div>
              <span className="font-sans text-sm font-bold block mb-1">Administrative Statistics Suspended</span>
              <p className="font-sans text-xs leading-relaxed opacity-90">
                To retrieve live token usage metrics, rate ceilings, and cost projections, you must input a valid API Key in the panel above.
              </p>
            </div>
          </div>
        )}

        {/* If Key is present, show Stats and Metrics */}
        {!isKeyMissing && (
          <>
            {/* 2. Real-time Metrics Cards */}
            <MetricsGrid health={health} costs={costs} />

            {/* 3. Cost & Quality Gate Graphs Row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <CostChart costs={costs} />
              </div>
              <div className="lg:col-span-1">
                <GateVerdictChart />
              </div>
            </div>

            {/* 4. Infrastructure Health Probes Checklist */}
            <HealthPanel health={health} />

            {/* 5. Contradiction Detection Evaluation Suite */}
            <MultiPerspectivePanel />
          </>
        )}
      </div>
    </Layout>
  );
}
