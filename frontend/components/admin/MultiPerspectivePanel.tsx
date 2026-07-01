"use client";
import React, { useState } from "react";
import { RAGApiClient } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Play, ShieldAlert, CheckCircle, BarChart2, Loader2 } from "lucide-react";

interface CategoryMetric {
  precision: number;
  recall: number;
  f1: number;
}

interface BenchmarkResult {
  total_cases: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
  false_positive_rate: number;
  llm_call_count: number;
  pre_filtered_count: number;
  type_metrics: Record<string, CategoryMetric>;
}

export default function MultiPerspectivePanel() {
  const { apiKey } = useStore();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BenchmarkResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runBenchmark = async () => {
    setLoading(true);
    setError(null);
    try {
      const api = new RAGApiClient("/api/proxy", apiKey);
      const data = await api.runContradictionBenchmark();
      setResult(data);
    } catch (err: any) {
      setError(err?.detail || err?.message || "Failed to execute benchmark. Administrative access required.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white border border-neutral-200 p-6 space-y-6">
      <div className="flex items-center justify-between pb-3 border-b border-neutral-100">
        <div>
          <h3 className="font-sans text-lg font-bold text-neutral-900">
            Contradiction Detection Evaluation Suite
          </h3>
          <p className="font-sans text-xs text-neutral-500">
            Run automated evaluation checks against the 50 standard multi-perspective research test cases.
          </p>
        </div>
        <button
          onClick={runBenchmark}
          disabled={loading}
          className="flex items-center gap-2 border border-neutral-900 bg-neutral-900 text-white font-mono text-xs uppercase tracking-wider px-4 py-2 hover:bg-white hover:text-neutral-900 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <>
              <Loader2 className="animate-spin" size={14} />
              Evaluating...
            </>
          ) : (
            <>
              <Play size={14} />
              Run Benchmark Suite
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2.5 bg-red-50 border border-red-200 p-4 text-xs font-sans text-red-700">
          <ShieldAlert className="shrink-0 mt-0.5" size={16} />
          <div>
            <span className="font-semibold block mb-0.5">Execution Failed</span>
            {error}
          </div>
        </div>
      )}

      {result && (
        <div className="space-y-6">
          {/* Main metric blocks */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-neutral-50 border border-neutral-200 p-4">
              <span className="font-mono text-[10px] text-neutral-500 uppercase block mb-1">Precision</span>
              <span className="font-mono text-2xl font-bold">{(result.precision * 100).toFixed(1)}%</span>
            </div>
            <div className="bg-neutral-50 border border-neutral-200 p-4">
              <span className="font-mono text-[10px] text-neutral-500 uppercase block mb-1">Recall</span>
              <span className="font-mono text-2xl font-bold">{(result.recall * 100).toFixed(1)}%</span>
            </div>
            <div className="bg-neutral-50 border border-neutral-200 p-4">
              <span className="font-mono text-[10px] text-neutral-500 uppercase block mb-1">F1-Score</span>
              <span className="font-mono text-2xl font-bold">{(result.f1 * 100).toFixed(1)}%</span>
            </div>
            <div className="bg-neutral-50 border border-neutral-200 p-4">
              <span className="font-mono text-[10px] text-neutral-500 uppercase block mb-1">False Positive Rate</span>
              <span className="font-mono text-2xl font-bold">{(result.false_positive_rate * 100).toFixed(1)}%</span>
            </div>
          </div>

          {/* Matrix table */}
          <div className="border border-neutral-200">
            <div className="bg-neutral-50 border-b border-neutral-200 p-3 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500">
              Confusion Matrix Detail
            </div>
            <table className="w-full font-mono text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-neutral-200 text-neutral-400">
                  <th className="p-3">True Positive</th>
                  <th className="p-3">False Positive</th>
                  <th className="p-3">True Negative</th>
                  <th className="p-3">False Negative</th>
                </tr>
              </thead>
              <tbody>
                <tr className="text-neutral-900">
                  <td className="p-3 border-r border-neutral-100">{result.tp}</td>
                  <td className="p-3 border-r border-neutral-100">{result.fp}</td>
                  <td className="p-3 border-r border-neutral-100">{result.tn}</td>
                  <td className="p-3">{result.fn}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Call Efficiency Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="border border-neutral-200 p-4 bg-white space-y-2">
              <h4 className="font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500 border-b border-neutral-100 pb-1">
                Pipeline Efficiency & Auditing
              </h4>
              <div className="flex justify-between font-mono text-xs">
                <span>LLM Audits Run:</span>
                <span className="font-bold">{result.llm_call_count}</span>
              </div>
              <div className="flex justify-between font-mono text-xs">
                <span>Embedding Pre-filtered Pairs:</span>
                <span className="font-bold">{result.pre_filtered_count}</span>
              </div>
            </div>
          </div>

          {/* Category Metrics */}
          <div className="border border-neutral-200">
            <div className="bg-neutral-50 border-b border-neutral-200 p-3 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-500">
              Contradiction Type Performance Breakdowns
            </div>
            <table className="w-full font-mono text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-neutral-200 text-neutral-400">
                  <th className="p-3">Category</th>
                  <th className="p-3">Precision</th>
                  <th className="p-3">Recall</th>
                  <th className="p-3">F1 Score</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.type_metrics).map(([cat, metrics]) => (
                  <tr key={cat} className="border-b border-neutral-100 hover:bg-neutral-50">
                    <td className="p-3 font-bold uppercase">{cat}</td>
                    <td className="p-3">{(metrics.precision * 100).toFixed(1)}%</td>
                    <td className="p-3">{(metrics.recall * 100).toFixed(1)}%</td>
                    <td className="p-3">{(metrics.f1 * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
