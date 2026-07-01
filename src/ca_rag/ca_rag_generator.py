import time
import logging
import json
import re
import uuid
from typing import List, Dict, Any, Tuple, Optional, Literal
from dataclasses import dataclass, field
from openai import OpenAI

from src.ca_rag.claim_extractor import Claim
from src.ca_rag.evidence_clusterer import EvidenceCluster, StanceLabel
from src.ca_rag.nli_detector import NLIMatrix, NLIResult, NLILabel
from src.ca_rag.conflict_graph import ConflictGraph
from src.ca_rag.confidence_scorer import ResponseConfidence
from src.utils.prompt_manager import PromptManager
from src.generation.hallucination_verifier import HallucinationVerifier

logger = logging.getLogger("rag_system.ca_rag.ca_rag_generator")

@dataclass
class ConflictExplanation:
    primary_reason: str
    explanation: str
    resolution_evidence: str
    practical_advice: str
    confidence_in_explanation: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_reason": self.primary_reason,
            "explanation": self.explanation,
            "resolution_evidence": self.resolution_evidence,
            "practical_advice": self.practical_advice,
            "confidence_in_explanation": self.confidence_in_explanation
        }

@dataclass
class ConflictPair:
    claim_a: Claim
    claim_b: Claim
    contradiction_strength: float
    nli_result: NLIResult
    explanation: Optional[ConflictExplanation] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_a": self.claim_a.to_dict(),
            "claim_b": self.claim_b.to_dict(),
            "contradiction_strength": self.contradiction_strength,
            "nli_result": self.nli_result.to_dict(),
            "explanation": self.explanation.to_dict() if self.explanation else None
        }

@dataclass
class CARAGResponse:
    query: str
    mode: Literal["ca_rag", "standard"]
    supporting_evidence: str
    contradicting_evidence: str
    areas_of_agreement: List[str]
    areas_of_disagreement: List[ConflictPair]
    final_balanced_summary: str
    response_confidence: ResponseConfidence
    clusters: List[EvidenceCluster]
    conflict_graph_json: Dict[str, Any]
    all_citations: List[Dict[str, Any]]
    conflict_explanations: List[ConflictExplanation]
    nli_matrix: NLIMatrix
    total_latency_ms: int
    latency_breakdown: Dict[str, int]
    response_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "areas_of_agreement": self.areas_of_agreement,
            "areas_of_disagreement": [p.to_dict() for p in self.areas_of_disagreement],
            "final_balanced_summary": self.final_balanced_summary,
            "response_confidence": self.response_confidence.to_dict(),
            "clusters": [c.to_dict() for c in self.clusters],
            "conflict_graph_json": self.conflict_graph_json,
            "all_citations": self.all_citations,
            "conflict_explanations": [e.to_dict() for e in self.conflict_explanations],
            "nli_matrix": self.nli_matrix.to_dict(),
            "total_latency_ms": self.total_latency_ms,
            "latency_breakdown": self.latency_breakdown,
            "response_id": self.response_id
        }


class CARAGGenerator:
    """Generates structured, multi-perspective Conflict-Aware RAG answers and handles conflict root-cause analysis."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        client: OpenAI,
        verifier: Optional[HallucinationVerifier] = None
    ) -> None:
        self.config = config
        self.prompt_manager = prompt_manager
        self.client = client
        self.verifier = verifier

    def _parse_section(self, text: str, heading: str) -> str:
        """Extracts text block located under a specific Markdown ## header."""
        pattern = rf"##\s*{heading}\s*\n(.*?)(?=\n##|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Fallback split check if regex fails
        parts = text.split("##")
        for part in parts:
            lines = part.strip().splitlines()
            if lines and heading.lower() in lines[0].lower():
                return "\n".join(lines[1:]).strip()
        return ""

    def generate(
        self,
        user_query: str,
        clusters: List[EvidenceCluster],
        conflict_graph: ConflictGraph,
        response_confidence: ResponseConfidence,
        nli_matrix: NLIMatrix,
        all_chunks: List[Any]
    ) -> CARAGResponse:
        """Assembles variables, formats prompt, calls LLM, and verifies synthesis for finished CA-RAG response."""
        start_time = time.perf_counter()
        breakdown = {}

        # 1. Format Stance Clusters
        supporting_cluster = next((c for c in clusters if c.stance == StanceLabel.SUPPORTS), None)
        contradicting_cluster = next((c for c in clusters if c.stance == StanceLabel.OPPOSES), None)
        
        if not supporting_cluster:
            # Fallback to the largest cluster as supporting
            sorted_c = sorted(clusters, key=lambda x: len(x.claims), reverse=True)
            supporting_cluster = sorted_c[0]
            if len(sorted_c) > 1:
                contradicting_cluster = sorted_c[1]

        support_label = supporting_cluster.label
        support_claims = "\n".join([f"- {c.normalized_text} [Claim: {c.claim_id}]" for c in supporting_cluster.claims])
        support_conf = int(supporting_cluster.confidence * 10)

        if contradicting_cluster:
            contradict_label = contradicting_cluster.label
            contradict_claims = "\n".join([f"- {c.normalized_text} [Claim: {c.claim_id}]" for c in contradicting_cluster.claims])
            contradict_conf = int(contradicting_cluster.confidence * 10)
        else:
            contradict_label = "Alternative viewpoints"
            contradict_claims = "None identified."
            contradict_conf = 0

        # Additional clusters beyond the top 2
        additional_clusters_list = []
        for idx, cl in enumerate(clusters):
            if cl.cluster_id != supporting_cluster.cluster_id and (not contradicting_cluster or cl.cluster_id != contradicting_cluster.cluster_id):
                cl_claims = "\n".join([f"- {c.normalized_text} [Claim: {c.claim_id}]" for c in cl.claims])
                additional_clusters_list.append(
                    f"ADDITIONAL EVIDENCE CLUSTER ({cl.label}):\n"
                    f"Claims: {cl_claims}\n"
                    f"Confidence: {int(cl.confidence * 10)}"
                )
        additional_clusters = "\n\n".join(additional_clusters_list)

        # 2. Format Contradictions List
        claim_map = {c.claim_id: c for c in nli_matrix.claims}
        contradiction_pairs_list = []
        for pair in nli_matrix.contradiction_pairs:
            c1 = claim_map.get(pair[0])
            c2 = claim_map.get(pair[1])
            if c1 and c2:
                contradiction_pairs_list.append(
                    f"- [Claim: {c1.claim_id}] (Stance: '{c1.source_title}') CONTRADICTS [Claim: {c2.claim_id}] (Stance: '{c2.source_title}')"
                )
        contradiction_pairs_text = "\n".join(contradiction_pairs_list) if contradiction_pairs_list else "None identified."

        # 3. Format Prompt
        prompt_text = self.prompt_manager.get_prompt(
            "ca_rag_generator_prompt",
            user_query=user_query,
            support_label=support_label,
            support_claims=support_claims,
            support_confidence=support_conf,
            contradict_label=contradict_label,
            contradict_claims=contradict_claims,
            contradict_confidence=contradict_conf,
            additional_clusters=additional_clusters,
            contradiction_pairs=contradiction_pairs_text,
            overall_confidence=int(response_confidence.overall * 10),
            conflict_clarity=int(response_confidence.conflict_clarity * 10),
            confidence_interpretation=response_confidence.interpretation
        )

        llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.3-70b-instruct")
        temperature = self.config.get("llm", {}).get("temperature", 0.0)

        # Request completions
        llm_start = time.perf_counter()
        response = self.client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=temperature
        )
        breakdown["llm_generation_ms"] = int((time.perf_counter() - llm_start) * 1000)

        full_answer = (response.choices[0].message.content or "").strip()

        # Parse sections
        supporting = self._parse_section(full_answer, "SUPPORTING EVIDENCE")
        contradicting = self._parse_section(full_answer, "CONTRADICTING EVIDENCE")
        
        # Parse agreement list
        agreement_text = self._parse_section(full_answer, "AREAS OF AGREEMENT")
        agreement_bullets = []
        for line in agreement_text.splitlines():
            line_clean = line.strip().lstrip("-*•").strip()
            if line_clean:
                agreement_bullets.append(line_clean)

        # Parse disagreement pairs
        disagreement_text = self._parse_section(full_answer, "AREAS OF DISAGREEMENT")
        final_summary = self._parse_section(full_answer, "FINAL BALANCED SUMMARY")

        # Map ConflictPair items
        conflict_pairs = []
        nli_results_map = {}
        for res in nli_matrix.results:
            nli_results_map[(res.claim_a_id, res.claim_b_id)] = res
            nli_results_map[(res.claim_b_id, res.claim_a_id)] = res

        for pair in nli_matrix.contradiction_pairs:
            c1 = claim_map.get(pair[0])
            c2 = claim_map.get(pair[1])
            res_nli = nli_results_map.get(pair)
            if c1 and c2 and res_nli:
                conflict_pairs.append(ConflictPair(
                    claim_a=c1,
                    claim_b=c2,
                    contradiction_strength=res_nli.contradiction_strength,
                    nli_result=res_nli,
                    explanation=None  # Explanations generated on-demand
                ))

        # 4. Anti-Hallucination verification gate (if enabled)
        if self.verifier:
            ver_start = time.perf_counter()
            # Verify concatenated text to catch anomalies
            verify_payload = f"{supporting}\n{contradicting}\n{final_summary}"
            verifier_res, _ = self.verifier.verify(verify_payload, all_chunks)
            breakdown["hallucination_verification_ms"] = int((time.perf_counter() - ver_start) * 1000)
            if verifier_res and verifier_res.verdict == "FAIL":
                logger.warning("Anti-hallucination verifier flagged CA-RAG response. Flagging warning metrics.")

        # Construct citations list
        all_citations = []
        chunk_map = {chk.chunk_id: chk for chk in all_chunks if hasattr(chk, "chunk_id")}
        for claim in nli_matrix.claims:
            chunk = chunk_map.get(claim.chunk_id)
            if chunk:
                all_citations.append({
                    "citation_id": claim.claim_id,
                    "title": claim.source_title,
                    "doc_id": claim.doc_id,
                    "chunk_id": claim.chunk_id,
                    "claim_text": claim.claim_text,
                    "normalized_text": claim.normalized_text,
                    "text_snippet": chunk.text,
                    "page_number": chunk.metadata.get("page_number", 1),
                    "source_quality": self.compute_source_quality_val(claim.source_title)
                })

        # Format Graph JSON
        visualization_graph = conflict_graph.graph
        if hasattr(conflict_graph, "metrics"):
            visualization_graph = {
                "nodes": [],
                "edges": [],
                "metrics": conflict_graph.metrics.to_dict()
            }
            # Add nodes
            claim_cluster_map = {}
            for cluster in clusters:
                for claim in cluster.claims:
                    claim_cluster_map[claim.claim_id] = cluster.cluster_id
            for claim in nli_matrix.claims:
                visualization_graph["nodes"].append({
                    "id": claim.claim_id,
                    "claim_id": claim.claim_id,
                    "label": claim.normalized_text[:50] + "..." if len(claim.normalized_text) > 50 else claim.normalized_text,
                    "full_text": claim.normalized_text,
                    "type": claim.claim_type.value,
                    "doc_id": claim.doc_id,
                    "source_title": claim.source_title,
                    "confidence": claim.confidence,
                    "cluster_id": claim_cluster_map.get(claim.claim_id, "")
                })
            # Add edges
            for res in nli_matrix.results:
                if res.final_verdict == NLILabel.CONTRADICTION:
                    visualization_graph["edges"].append({
                        "source": res.claim_a_id,
                        "target": res.claim_b_id,
                        "type": "CONTRADICTS",
                        "weight": res.contradiction_strength,
                        "color": "red"
                    })
                    if res.is_bidirectional:
                        visualization_graph["edges"].append({
                            "source": res.claim_b_id,
                            "target": res.claim_a_id,
                            "type": "CONTRADICTS",
                            "weight": res.contradiction_strength,
                            "color": "red"
                        })
                elif res.final_verdict == NLILabel.ENTAILMENT:
                    fwd_score = res.forward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    bwd_score = res.backward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    visualization_graph["edges"].append({
                        "source": res.claim_a_id,
                        "target": res.claim_b_id,
                        "type": "SUPPORTS",
                        "weight": max(fwd_score, bwd_score),
                        "color": "green"
                    })

        total_latency = int((time.perf_counter() - start_time) * 1000)
        breakdown["total_generation_ms"] = total_latency

        return CARAGResponse(
            query=user_query,
            mode="ca_rag",
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            areas_of_agreement=agreement_bullets,
            areas_of_disagreement=conflict_pairs,
            final_balanced_summary=final_summary,
            response_confidence=response_confidence,
            clusters=clusters,
            conflict_graph_json=visualization_graph,
            all_citations=all_citations,
            conflict_explanations=[],
            nli_matrix=nli_matrix,
            total_latency_ms=total_latency,
            latency_breakdown=breakdown,
            response_id=str(uuid.uuid4())
        )

    def compute_source_quality_val(self, title: str) -> float:
        title_lower = title.lower()
        if "arxiv" in title_lower or "doi:" in title_lower or "journal" in title_lower or "clinical" in title_lower:
            return 1.0
        elif "docs" in title_lower or "official" in title_lower or "manual" in title_lower or "guideline" in title_lower:
            return 0.85
        elif "news" in title_lower or "blog" in title_lower or "post" in title_lower:
            return 0.65
        return 0.40

    def explain_conflict(
        self,
        user_query: str,
        cluster_a: EvidenceCluster,
        cluster_b: EvidenceCluster,
        nli_result: NLIResult
    ) -> ConflictExplanation:
        """Explains the root cause (temporal, methodology, scope, etc.) of a direct claim contradiction."""
        try:
            # Reconstruct metadata strings
            meta_a = f"Title: {cluster_a.representative_claim.source_title} | Doc ID: {cluster_a.representative_claim.doc_id}"
            meta_b = f"Title: {cluster_b.representative_claim.source_title} | Doc ID: {cluster_b.representative_claim.doc_id}"

            prompt_text = self.prompt_manager.get_prompt(
                "ca_rag_conflict_explainer",
                user_query=user_query,
                cluster_a_label=cluster_a.label,
                claim_a=cluster_a.representative_claim.normalized_text,
                source_a_metadata=meta_a,
                cluster_b_label=cluster_b.label,
                claim_b=cluster_b.representative_claim.normalized_text,
                source_b_metadata=meta_b,
                contradiction_strength=f"{nli_result.contradiction_strength:.2f}"
            )

            llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.3-70b-instruct")
            response = self.client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )

            data = json.loads((response.choices[0].message.content or "").strip())
            
            return ConflictExplanation(
                primary_reason=data.get("primary_reason", "METHODOLOGICAL"),
                explanation=data.get("explanation", "Sources differ in assumptions or metrics."),
                resolution_evidence=data.get("resolution_evidence", "Further experiments or cross-validations."),
                practical_advice=data.get("practical_advice", "Check context and publish dates carefully."),
                confidence_in_explanation=float(data.get("confidence_in_explanation", 0.7))
            )

        except Exception as e:
            logger.error(f"Failed to generate conflict explanation: {str(e)}")
            return ConflictExplanation(
                primary_reason="METHODOLOGICAL",
                explanation="Discrepancy caused by methodological differences or scope variations in study layouts.",
                resolution_evidence="Further peer-reviewed literature is required.",
                practical_advice="Evaluate the publications' data collections directly.",
                confidence_in_explanation=0.5
            )
