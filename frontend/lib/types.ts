export enum ConfidenceLevel {
  HIGH = "High",
  MEDIUM = "Medium",
  LOW = "Low"
}

export enum GateVerdict {
  SUFFICIENT = "SUFFICIENT",
  PARTIAL = "PARTIAL",
  INSUFFICIENT = "INSUFFICIENT",
  PASS = "PASS",
  FAIL = "FAIL"
}

export enum MessageRole {
  USER = "user",
  ASSISTANT = "assistant"
}

export interface Source {
  chunk_id: string;
  text: string;
  score: number;
  metadata: {
    title?: string;
    page_number?: number;
    doc_id?: string;
    [key: string]: any;
  };
}

export interface QualityGatesResponse {
  preflight: {
    verdict: string;
    reason: string;
    gaps: string[];
  };
  hallucination_verifier: {
    verdict: string | null;
    audit: Array<{
      claim: string;
      supported: boolean;
      evidence: string;
    }>;
  };
}

export interface RAGResponse {
  query: string;
  answer: string;
  sources: Source[];
  confidence: string; // "High" | "Medium" | "Low"
  missing_information: string;
  quality_gates: QualityGatesResponse;
  latencies: Record<string, number>;
  mode?: "standard" | "multi_perspective";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: RAGResponse | MultiPerspectiveRAGResponse;
  timestamp: number;
  error?: string;
}

export interface Document {
  doc_id: string;
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  chunks_count: number;
  indexed_at: string;
}

export type IngestionStatus = "idle" | "uploading" | "chunking" | "embedding" | "success" | "error";

export interface IngestionProgress {
  id: string;
  file_name: string;
  status: IngestionStatus;
  progress: number;
  chunks_count?: number;
  error?: string;
}

export type ComponentStatus = "healthy" | "degraded" | "offline";

export interface HealthStatus {
  status: "healthy" | "degraded" | "offline";
  checks: Record<string, string>;
  circuit_breaker?: {
    state: "CLOSED" | "OPEN" | "HALF-OPEN";
    consecutive_failures: number;
  };
  cache?: {
    hits: number;
    misses: number;
    hit_rate: string;
    active_entries_count: number;
  };
  queue?: {
    depth: number;
    limit: number;
    concurrency_limit: number;
  };
}

export interface KeyUsageStats {
  tier: string;
  daily_tokens_used: number;
  daily_token_limit: number;
  daily_budget_pct: string;
  estimated_daily_cost_usd: number;
  monthly_tokens_used: number;
  monthly_token_limit: number;
  monthly_budget_pct: string;
  estimated_monthly_cost_usd: number;
}

export interface CostReport {
  timestamp: string;
  pricing_model: {
    prompt_tokens_per_million: number;
    completion_tokens_per_million: number;
  };
  api_keys_usage: Record<string, KeyUsageStats>;
}

export interface QueryRequest {
  query: string;
}

export interface APIErrorResponse {
  detail: string | Array<{ msg: string; loc: string[] }>;
}

export class APIError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API Error ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
    Object.setPrototypeOf(this, APIError.prototype);
  }
}

// --- Phase 6 Multi-Perspective Types ---

export interface ContradictionResult {
  is_contradiction: boolean;
  confidence: number;
  contradiction_type: string | null;
  claim_a: string;
  claim_b: string;
  explanation: string;
  chunk_a_id: string;
  chunk_b_id: string;
}

export interface Perspective {
  chunk_id: string;
  source: string;
  position: string;
  key_evidence: string;
  source_confidence: string;
  caveats: string;
  stance_label: string;
}

export interface PerspectiveCluster {
  cluster_id: string;
  label: string;
  perspectives: Perspective[];
  representative_chunk_id: string;
  chunk_count: number;
  avg_confidence: number;
}

export interface DisagreementScore {
  raw_score: number;
  display_score: number;
  interpretation: string;
  dominant_perspective: string;
  minority_perspective: string;
}

export interface MultiPerspectiveRAGResponse {
  response_id: string;
  mode: "standard" | "multi_perspective";
  answer: string;
  perspectives: PerspectiveCluster[];
  contradictions: ContradictionResult[];
  disagreement_score: DisagreementScore;
  sources: Source[];
  confidence: string;
  total_latency_ms: number;
  latency_breakdown: Record<string, number>;
  query?: string;
  missing_information?: string;
  quality_gates?: QualityGatesResponse;
  latencies?: Record<string, number>;
}

export interface EvidenceCluster extends PerspectiveCluster {
  text?: string;
}

export interface ClusterConfidence {
  relevance: number;
  quality: number;
  citations: number;
  freshness: number;
  contradiction: number;
}

export interface ToastInfo {
  id: string;
  type: "success" | "error" | "warning" | "info";
  title: string;
  description?: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export interface QueryInputProps {
  onSubmit: (query: string) => void;
  isLoading: boolean;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  showCharCount?: boolean;
  onClear?: () => void;
}

export interface DisagreementMeterProps {
  score: number;
  interpretation: string;
  size: "sm" | "md" | "lg";
  showLabel?: boolean;
  showInterpretation?: boolean;
  animated?: boolean;
  isLoading?: boolean;
}

export interface CitationPillProps {
  docTitle: string;
  chunkId: string;
  docId: string;
  claimId?: string;
  onClick?: (chunkId: string) => void;
  isActive?: boolean;
  isContradicting?: boolean;
  excerpt?: string; // Optional excerpt for tooltip hover
}

export interface EvidenceColumnProps {
  cluster: EvidenceCluster;
  perspective: "A" | "B" | "C" | "D";
  isHighlighted?: boolean;
  onClaimClick?: (claimId: string) => void;
  onSourceClick?: (chunkId: string) => void;
  totalClusters: number;
  isLoading?: boolean;
}

export interface ConflictBannerProps {
  disagreementScore: DisagreementScore;
  contradictionCount: number;
  clusterCount: number;
  onExplain?: () => void;
  isExplainLoading?: boolean;
  explanationText?: string; // Loaded explanation detail
}

export interface SourceCardProps {
  source: Source;
  isActive?: boolean;
  clusterColor?: string;
  onExpand?: () => void;
  rank: number;
  isContradicting?: boolean;
  isLoading?: boolean;
}

export type SkeletonVariant =
  | "message"
  | "ca-rag-response"
  | "source-card"
  | "evidence-column"
  | "metrics-grid"
  | "text-line"
  | "paragraph";

export interface SkeletonLoaderProps {
  variant: SkeletonVariant;
  count?: number;
  animated?: boolean;
}

export type EmptyStateVariant =
  | "no-messages"
  | "no-documents"
  | "no-results"
  | "no-contradictions"
  | "error"
  | "offline";

export interface EmptyStateProps {
  variant: EmptyStateVariant;
  title?: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  exampleChips?: string[]; // Custom list of query chips for no-messages variant
}

export interface ResponseConfidenceModel {
  overall: number;
  dominant_cluster_confidence: number;
  minority_cluster_confidence: number;
  conflict_clarity: number;
  interpretation: string;
  recommendation: string;
}

export interface ConfidenceRadarProps {
  supportingCluster?: ClusterConfidence;
  contradictingCluster?: ClusterConfidence;
  confidence?: ResponseConfidenceModel;
  size?: number;
  showLegend?: boolean;
  showValues?: boolean;
  isLoading?: boolean;
}

export interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}
