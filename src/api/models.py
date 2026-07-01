from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class QueryRequest(BaseModel):
    """Payload representing a natural language question query request."""
    query: str = Field(
        ...,
        min_length=1,
        description="The natural language question to process.",
        json_schema_extra={"example": "What is the hybrid search threshold?"}
    )


class PreflightVerdict(BaseModel):
    """Preflight check result describing retrieval sufficiency quality gates."""
    verdict: str = Field(..., description="Sufficiency classification: SUFFICIENT | PARTIAL | INSUFFICIENT")
    reason: str = Field(..., description="Description of the sufficiency evaluation result.")
    gaps: List[str] = Field(default_factory=list, description="Details of missing information components.")


class HallucinationAuditItem(BaseModel):
    """Audited details for a single claim made in the generated answer."""
    claim: str = Field(..., description="The assertion statement.")
    supported: bool = Field(..., description="True if verified by the retrieved context.")
    evidence: str = Field(..., description="Relevant quote or explanation.")


class HallucinationVerifierResult(BaseModel):
    """Result from the anti-hallucination verification audit."""
    verdict: Optional[str] = Field(None, description="Verification status: PASS | FAIL | None")
    audit: List[HallucinationAuditItem] = Field(default_factory=list, description="Audited claims checklist.")


class QualityGatesResponse(BaseModel):
    """Aggregate of system quality gates evaluation outputs."""
    preflight: PreflightVerdict
    hallucination_verifier: HallucinationVerifierResult


class QueryResponse(BaseModel):
    """Structured response object containing query answers, citations, and quality metadata."""
    query: str = Field(..., description="The original search query.")
    answer: str = Field(..., description="Synthesized text answer.")
    sources: List[str] = Field(default_factory=list, description="Citations and references used.")
    confidence: str = Field(..., description="Confidence estimation category: High | Medium | Low")
    missing_information: str = Field(..., description="Description of missing context aspects.")
    quality_gates: QualityGatesResponse = Field(..., description="Details of quality check verifications.")
    latencies: Dict[str, float] = Field(..., description="Detailed latency breakdown of stage processes (ms).")


class IngestRequest(BaseModel):
    """Payload representing a request to ingest a local document."""
    file_path: str = Field(
        ...,
        min_length=1,
        description="The absolute path of the local file (PDF, DOCX, TXT, MD) to load.",
        json_schema_extra={"example": "d:/multipurposerag/data/sample.pdf"}
    )


class IngestResponse(BaseModel):
    """Metadata response confirming completion of the document ingestion pipeline."""
    status: str = Field(..., description="Status string: success | error")
    doc_id: Optional[str] = Field(None, description="Hex document ID derived from file hash.")
    chunks_count: int = Field(..., description="Number of database indexed chunks created.")
    message: str = Field(..., description="Human readable transaction outcome note.")


class HealthResponse(BaseModel):
    """System health check and database statistics payload."""
    status: str = Field(..., description="Component state: healthy")
    collection_stats: Dict[str, Any] = Field(..., description="Statistics of vector storage database.")


class PromptsResponse(BaseModel):
    """Definitions of prompts active in PromptManager config."""
    prompts: Dict[str, Any] = Field(..., description="Active system prompt templates keyed by name.")


# --- Phase 6 Multi-Perspective Models ---

class ContradictionResultItem(BaseModel):
    is_contradiction: bool
    confidence: float
    contradiction_type: Optional[str]
    claim_a: str
    claim_b: str
    explanation: str
    chunk_a_id: str
    chunk_b_id: str


class PerspectiveItem(BaseModel):
    chunk_id: str
    source: str
    position: str
    key_evidence: str
    source_confidence: str
    caveats: str
    stance_label: str


class PerspectiveClusterItem(BaseModel):
    cluster_id: str
    label: str
    perspectives: List[PerspectiveItem]
    representative_chunk_id: str
    chunk_count: int
    avg_confidence: float


class DisagreementScoreItem(BaseModel):
    raw_score: float
    display_score: int
    interpretation: str
    dominant_perspective: str
    minority_perspective: str


class MultiPerspectiveQueryResponse(BaseModel):
    response_id: str
    mode: str
    answer: str
    perspectives: List[PerspectiveClusterItem]
    contradictions: List[ContradictionResultItem]
    disagreement_score: DisagreementScoreItem
    sources: List[Dict[str, Any]]
    confidence: str
    total_latency_ms: int
    latency_breakdown: Dict[str, float]


class ExplainDisagreementRequest(BaseModel):
    query: str
    response_id: str


class ExplainDisagreementResponse(BaseModel):
    explanation: str
    latency_ms: int


class CategoryMetric(BaseModel):
    precision: float
    recall: float
    f1: float


class ContradictionBenchmarkResponse(BaseModel):
    total_cases: int
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    llm_call_count: int
    pre_filtered_count: int
    type_metrics: Dict[str, CategoryMetric]


# --- Phase 6 CA-RAG Models ---

class ClaimModel(BaseModel):
    claim_id: str
    chunk_id: str
    doc_id: str
    source_title: str
    claim_text: str
    normalized_text: str
    claim_type: str
    confidence: float
    span_start: int
    span_end: int


class NLIResultModel(BaseModel):
    claim_a_id: str
    claim_b_id: str
    forward_label: str
    forward_scores: Dict[str, float]
    backward_label: str
    backward_scores: Dict[str, float]
    final_verdict: str
    contradiction_strength: float
    is_bidirectional: bool


class EvidenceClusterModel(BaseModel):
    cluster_id: str
    label: str
    stance: str
    claims: List[ClaimModel]
    representative_claim: ClaimModel
    source_count: int
    chunk_ids: List[str]
    doc_ids: List[str]
    confidence: float
    internal_consistency: float


class ConflictExplanationModel(BaseModel):
    primary_reason: str
    explanation: str
    resolution_evidence: str
    practical_advice: str
    confidence_in_explanation: float


class ConflictPairModel(BaseModel):
    claim_a: ClaimModel
    claim_b: ClaimModel
    contradiction_strength: float
    nli_result: NLIResultModel
    explanation: Optional[ConflictExplanationModel] = None


class ResponseConfidenceModel(BaseModel):
    overall: float
    dominant_cluster_confidence: float
    minority_cluster_confidence: float
    conflict_clarity: float
    interpretation: str
    recommendation: str


class CARAGResponseModel(BaseModel):
    query: str
    mode: str
    supporting_evidence: str
    contradicting_evidence: str
    areas_of_agreement: List[str]
    areas_of_disagreement: List[ConflictPairModel]
    final_balanced_summary: str
    response_confidence: ResponseConfidenceModel
    clusters: List[EvidenceClusterModel]
    conflict_graph_json: Dict[str, Any]
    all_citations: List[Dict[str, Any]]
    total_latency_ms: int
    latency_breakdown: Dict[str, float]
    response_id: str


class ExplainConflictRequest(BaseModel):
    response_id: str
    claim_a_id: str
    claim_b_id: str


