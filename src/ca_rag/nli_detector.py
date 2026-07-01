import time
import logging
import json
from enum import Enum
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np
from openai import OpenAI

from src.ca_rag.claim_extractor import Claim

logger = logging.getLogger("rag_system.ca_rag.nli_detector")

class NLILabel(str, Enum):
    ENTAILMENT = "ENTAILMENT"
    CONTRADICTION = "CONTRADICTION"
    NEUTRAL = "NEUTRAL"

@dataclass
class NLIResult:
    claim_a_id: str
    claim_b_id: str
    forward_label: NLILabel
    forward_scores: Dict[str, float]
    backward_label: NLILabel
    backward_scores: Dict[str, float]
    final_verdict: NLILabel
    contradiction_strength: float
    is_bidirectional: bool
    model_used: str
    inference_time_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_a_id": self.claim_a_id,
            "claim_b_id": self.claim_b_id,
            "forward_label": self.forward_label.value,
            "forward_scores": self.forward_scores,
            "backward_label": self.backward_label.value,
            "backward_scores": self.backward_scores,
            "final_verdict": self.final_verdict.value,
            "contradiction_strength": self.contradiction_strength,
            "is_bidirectional": self.is_bidirectional,
            "model_used": self.model_used,
            "inference_time_ms": self.inference_time_ms
        }

@dataclass
class NLIMatrix:
    claims: List[Claim]
    results: List[NLIResult]
    contradiction_pairs: List[Tuple[str, str]]
    entailment_pairs: List[Tuple[str, str]]
    neutral_pairs: List[Tuple[str, str]]
    has_contradictions: bool
    contradiction_density: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "contradiction_pairs": self.contradiction_pairs,
            "entailment_pairs": self.entailment_pairs,
            "neutral_pairs": self.neutral_pairs,
            "has_contradictions": self.has_contradictions,
            "contradiction_density": self.contradiction_density
        }


class NLIContradictionDetector:
    """Uses Natural Language Inference to evaluate relationships (Entailment, Contradiction, Neutral) between claim pairs."""

    def __init__(
        self,
        config: Dict[str, Any],
        vector_store: Any,
        client: OpenAI
    ) -> None:
        self.config = config
        self.vector_store = vector_store
        self.client = client
        
        ca_config = config.get("ca_rag", {})
        self.model_name = ca_config.get("nli_model_name", "cross-encoder/nli-deberta-v3-base")
        self.fallback_model_name = ca_config.get("fallback_nli_model_name", "facebook/bart-large-mnli")
        self.similarity_min = ca_config.get("nli_similarity_min", 0.25)
        self.contradiction_threshold = ca_config.get("contradiction_threshold", 0.55)
        
        self.model = None
        self.label_mapping: Dict[int, NLILabel] = {}
        self._init_nli_model()

    def _init_nli_model(self) -> None:
        """Attempts to load primary or fallback local CrossEncoder NLI models."""
        try:
            from sentence_transformers import CrossEncoder
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"NLI device: {device}")
            self.model = CrossEncoder(
                "cross-encoder/nli-deberta-v3-base",
                device=device,
                max_length=512
            )
            self._build_label_mapping(self.model, self.model_name)
        except Exception as e:
            logger.warning(f"Failed to load primary NLI model {self.model_name}: {str(e)}. Loading fallback {self.fallback_model_name}...")
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(self.fallback_model_name)
                self._build_label_mapping(self.model, self.fallback_model_name)
            except Exception as ex:
                logger.error(f"Failed to load fallback NLI model: {str(ex)}. NLI Contradiction Detector will fall back to LLM queries.")
                self.model = None

    def _build_label_mapping(self, model: Any, model_name: str) -> None:
        """Parses model config to map class indices to logic labels: Entailment, Contradiction, Neutral."""
        self.label_mapping = {}
        try:
            # Check id2label in HF config
            if hasattr(model, "model") and hasattr(model.model, "config") and hasattr(model.model.config, "id2label"):
                id2label = model.model.config.id2label
                for idx, val in id2label.items():
                    val_lower = str(val).lower()
                    if "contradict" in val_lower:
                        self.label_mapping[idx] = NLILabel.CONTRADICTION
                    elif "entail" in val_lower or "support" in val_lower:
                        self.label_mapping[idx] = NLILabel.ENTAILMENT
                    else:
                        self.label_mapping[idx] = NLILabel.NEUTRAL
        except Exception as e:
            logger.warning(f"Could not parse label mapping dynamically: {str(e)}. Using static maps.")
        
        # Fallbacks if metadata label parse failed
        if not self.label_mapping:
            if "deberta" in model_name.lower():
                # deberta default: 0=entailment, 1=neutral, 2=contradiction
                self.label_mapping = {0: NLILabel.ENTAILMENT, 1: NLILabel.NEUTRAL, 2: NLILabel.CONTRADICTION}
            elif "bart" in model_name.lower() or "mnli" in model_name.lower():
                # bart default: 0=contradiction, 1=neutral, 2=entailment
                self.label_mapping = {0: NLILabel.CONTRADICTION, 1: NLILabel.NEUTRAL, 2: NLILabel.ENTAILMENT}
            else:
                # Default guess
                self.label_mapping = {0: NLILabel.ENTAILMENT, 1: NLILabel.NEUTRAL, 2: NLILabel.CONTRADICTION}
        logger.info(f"Loaded label mapping for {model_name}: {self.label_mapping}")

    def _cosine_similarity(self, u: List[float], v: List[float]) -> float:
        if not u or not v:
            return 0.0
        arr_u, arr_v = np.array(u), np.array(v)
        norm_u = np.linalg.norm(arr_u)
        norm_v = np.linalg.norm(arr_v)
        if norm_u == 0 or norm_v == 0:
            return 0.0
        return float(np.dot(arr_u, arr_v) / (norm_u * norm_v))

    def _predict_local(self, pairs: List[Tuple[str, str]]) -> List[Dict[str, float]]:
        """Invokes local CrossEncoder prediction, returning probability scores for each label."""
        if not self.model:
            return []
        
        # CrossEncoder predicts raw scores or logits
        raw_outputs = self.model.predict(pairs)
        
        results = []
        for scores in raw_outputs:
            # Softmax to get probability distribution
            exp_scores = np.exp(scores - np.max(scores))
            probs = exp_scores / np.sum(exp_scores)
            
            prob_dict = {NLILabel.ENTAILMENT.value: 0.0, NLILabel.CONTRADICTION.value: 0.0, NLILabel.NEUTRAL.value: 0.0}
            for idx, prob in enumerate(probs):
                label = self.label_mapping.get(idx, NLILabel.NEUTRAL)
                prob_dict[label.value] = float(prob)
            results.append(prob_dict)
        return results

    def _predict_llm(self, premise: str, hypothesis: str) -> Dict[str, float]:
        """Alternative LLM auditor executing NLI classification when local models are unavailable."""
        prompt = f"""Given the Premise statement and the Hypothesis statement, analyze their relationship.
Determine the probability (between 0.0 and 1.0) that:
1. ENTAILMENT: The Premise logically implies that the Hypothesis is True.
2. CONTRADICTION: The Premise and the Hypothesis cannot both be True simultaneously.
3. NEUTRAL: The Premise and Hypothesis are independent or talk about different aspects.

Premise: {premise}
Hypothesis: {hypothesis}

Respond ONLY with JSON format containing the scores (they must sum to 1.0):
{{
  "entailment": <float>,
  "contradiction": <float>,
  "neutral": <float>
}}"""
        try:
            llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.3-70b-instruct")
            response = self.client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content.strip())
            return {
                NLILabel.ENTAILMENT.value: float(data.get("entailment", 0.0)),
                NLILabel.CONTRADICTION.value: float(data.get("contradiction", 0.0)),
                NLILabel.NEUTRAL.value: float(data.get("neutral", 1.0))
            }
        except Exception as e:
            logger.error(f"LLM NLI prediction failed: {str(e)}")
            return {NLILabel.ENTAILMENT.value: 0.0, NLILabel.CONTRADICTION.value: 0.0, NLILabel.NEUTRAL.value: 1.0}

    def compute_contradiction_strength(self, fwd: Dict[str, float], bwd: Dict[str, float], cos_sim: float) -> Tuple[float, bool]:
        """Calculates contradiction strength: score * bidirectionality_bonus * semantic similarity multiplier."""
        fwd_c = fwd.get(NLILabel.CONTRADICTION.value, 0.0)
        bwd_c = bwd.get(NLILabel.CONTRADICTION.value, 0.0)
        
        is_bidirectional = (fwd_c >= self.contradiction_threshold) and (bwd_c >= self.contradiction_threshold)
        
        # Max of both directions for contradiction score
        base_score = max(fwd_c, bwd_c)
        
        # Apply 20% bonus if disagreement is mutual (bidirectional)
        bi_bonus = 1.2 if is_bidirectional else 1.0
        
        # Similar claims that contradict represent stronger contradictions
        strength = base_score * bi_bonus * cos_sim
        return min(max(strength, 0.0), 1.0), is_bidirectional

    def classify_pair(self, claim_a: Claim, claim_b: Claim, cos_sim: float) -> NLIResult:
        """Determines relationship label and strength for a claim pair."""
        start_time = time.perf_counter()
        
        if self.model:
            # Batch predict both directions in one go
            pairs = [(claim_a.normalized_text, claim_b.normalized_text), (claim_b.normalized_text, claim_a.normalized_text)]
            scores = self._predict_local(pairs)
            fwd_scores, bwd_scores = scores[0], scores[1]
            model_used = self.model_name if self.model else "LLM-fallback"
        else:
            fwd_scores = self._predict_llm(claim_a.normalized_text, claim_b.normalized_text)
            bwd_scores = self._predict_llm(claim_b.normalized_text, claim_a.normalized_text)
            model_used = "LLM-fallback"

        # Determine best labels
        fwd_label_str = max(fwd_scores, key=lambda k: fwd_scores[k])
        bwd_label_str = max(bwd_scores, key=lambda k: bwd_scores[k])
        
        fwd_label = NLILabel(fwd_label_str.upper())
        bwd_label = NLILabel(bwd_label_str.upper())

        strength, is_bidirectional = self.compute_contradiction_strength(fwd_scores, bwd_scores, cos_sim)
        
        # Deduce final verdict label
        if is_bidirectional:
            final_verdict = NLILabel.CONTRADICTION
        elif fwd_label == NLILabel.ENTAILMENT or bwd_label == NLILabel.ENTAILMENT:
            final_verdict = NLILabel.ENTAILMENT
        elif fwd_label == NLILabel.CONTRADICTION or bwd_label == NLILabel.CONTRADICTION:
            # Unidirectional contradiction
            final_verdict = NLILabel.CONTRADICTION
        else:
            final_verdict = NLILabel.NEUTRAL

        latency = int((time.perf_counter() - start_time) * 1000)
        
        return NLIResult(
            claim_a_id=claim_a.claim_id,
            claim_b_id=claim_b.claim_id,
            forward_label=fwd_label,
            forward_scores=fwd_scores,
            backward_label=bwd_label,
            backward_scores=bwd_scores,
            final_verdict=final_verdict,
            contradiction_strength=strength,
            is_bidirectional=is_bidirectional,
            model_used=model_used,
            inference_time_ms=latency
        )

    def classify_all(self, claims: List[Claim]) -> NLIMatrix:
        """Runs pairwise relationship verification on all compatible claim combinations."""
        results = []
        contradiction_pairs = []
        entailment_pairs = []
        neutral_pairs = []
        
        n_claims = len(claims)
        total_possible = (n_claims * (n_claims - 1)) // 2 if n_claims > 1 else 1

        for i in range(n_claims):
            for j in range(i + 1, n_claims):
                c1, c2 = claims[i], claims[j]
                
                # Check pre-filter: cannot contradict if from same chunk
                if c1.chunk_id == c2.chunk_id:
                    continue
                
                # Check pre-filter: cosine similarity threshold
                cos_sim = self._cosine_similarity(c1.embedding, c2.embedding)
                if cos_sim < self.similarity_min:
                    # Treat as NEUTRAL directly, skip model execution
                    continue

                res = self.classify_pair(c1, c2, cos_sim)
                results.append(res)

                pair_tuple = (c1.claim_id, c2.claim_id)
                if res.final_verdict == NLILabel.CONTRADICTION:
                    contradiction_pairs.append(pair_tuple)
                elif res.final_verdict == NLILabel.ENTAILMENT:
                    entailment_pairs.append(pair_tuple)
                else:
                    neutral_pairs.append(pair_tuple)

        has_contradictions = len(contradiction_pairs) > 0
        contradiction_density = len(contradiction_pairs) / total_possible if total_possible > 0 else 0.0

        return NLIMatrix(
            claims=claims,
            results=results,
            contradiction_pairs=contradiction_pairs,
            entailment_pairs=entailment_pairs,
            neutral_pairs=neutral_pairs,
            has_contradictions=has_contradictions,
            contradiction_density=contradiction_density
        )
