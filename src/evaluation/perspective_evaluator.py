import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from src.evaluation.evaluator import RAGEvaluator
from src.multiperspective.pipeline import MultiPerspectiveRAGPipeline, MultiPerspectiveRAGResponse

# Initialize logging
logger = logging.getLogger("rag_system.evaluation.perspective_evaluator")


class PerspectiveEvaluator(RAGEvaluator):
    """Evaluates the multi-perspective RAG pipeline for stance coverage, contradiction detection, and citation accuracy."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: Any,
        pipeline: MultiPerspectiveRAGPipeline,
        client: Optional[Any] = None
    ) -> None:
        super().__init__(config, prompt_manager, pipeline, client)
        self.pipeline = pipeline  # Cast to MultiPerspectiveRAGPipeline
        
        # Load multi-perspective specific thresholds
        eval_conf = config.get("evaluation", {})
        self.mp_thresholds = eval_conf.get("mp_thresholds", {
            "stance_coverage": 4.0,              # 1-5 scale
            "disagreement_calibration": 3.8,      # 1-5 scale
            "contradiction_accuracy": 0.8,       # 0-1 scale
            "citation_quality": 4.0              # 1-5 scale
        })

    def load_mp_dataset(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Loads the multi-perspective evaluation dataset."""
        dataset_path = path or self.config.get("evaluation", {}).get(
            "multiperspective_dataset_path", "data/golden_dataset/multiperspective_qa_pairs.json"
        )
        if not os.path.exists(dataset_path):
            raise FileNotFoundError(f"Multi-perspective dataset not found at: {dataset_path}")
        
        with open(dataset_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def evaluate_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates a single multi-perspective case."""
        query = case["query"]
        ground_truth_stances = case.get("ground_truth_stances", [])
        expected_disagreement = case.get("expected_disagreement_score", 0.0)

        # Run pipeline
        response: MultiPerspectiveRAGResponse = await self.pipeline.query(query)  # type: ignore[attr-defined]

        # Evaluate stance coverage and correctness via LLM-as-a-judge
        judge_prompt = f"""
You are an objective auditor evaluating a Multi-Perspective RAG system's answer.
Query: {query}
Generated Answer: {response.answer}
Detected Stance Clusters:
{json.dumps([{'label': c.label, 'representative_chunk': c.representative_chunk_id} for c in response.perspectives], indent=2)}

Ground Truth Expected Stances:
{json.dumps(ground_truth_stances, indent=2)}

Please evaluate the answer across the following dimensions on a scale of 1.0 to 5.0 (decimals allowed):
1. Stance Coverage: Did the generated answer cover all the ground truth perspectives accurately without bias?
2. Disagreement Calibration: The generated answer reported a disagreement score of {response.disagreement_score.display_score}/10 (interpretation: {response.disagreement_score.interpretation}). The expected disagreement score is {expected_disagreement}/10. Does this score calibrate well with the actual text conflict?
3. Citation Quality: Are claims in the stances properly supported by direct citations to retrieved sources?

Respond strictly in valid JSON format with this structure:
{{
  "stance_coverage": 4.5,
  "disagreement_calibration": 4.0,
  "citation_quality": 4.5,
  "rationale": "Detailed explanation..."
}}
"""
        try:
            judge_res = self.client.chat.completions.create(
                model=self.config.get("llm", {}).get("model", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "You are a professional RAG evaluator. Output JSON only."},
                    {"role": "user", "content": judge_prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            scores = json.loads(judge_res.choices[0].message.content)
        except Exception as e:
            logger.error(f"LLM-as-a-judge scoring failed: {str(e)}")
            scores = {
                "stance_coverage": 1.0,
                "disagreement_calibration": 1.0,
                "citation_quality": 1.0,
                "rationale": f"Scoring failed due to LLM error: {str(e)}"
            }

        # Calculate contradiction metrics if contradictions are present in ground truth
        expected_contradiction = case.get("has_contradiction", False)
        actual_contradiction = any(c.is_contradiction for c in response.contradictions)
        
        # 1.0 if match, 0.0 if mismatch
        contradiction_match = 1.0 if expected_contradiction == actual_contradiction else 0.0

        return {
            "query": query,
            "response_id": response.response_id,
            "answer": response.answer,
            "disagreement_score": response.disagreement_score.display_score,
            "expected_disagreement": expected_disagreement,
            "scores": scores,
            "contradiction_match": contradiction_match,
            "latency_ms": response.total_latency_ms
        }

    async def run_evaluation(self, dataset_path: Optional[str] = None) -> Dict[str, Any]:  # type: ignore[override]
        """Runs the entire evaluation suite over all loaded cases."""
        cases = self.load_mp_dataset(dataset_path)
        results = []
        
        for case in cases:
            res = await self.evaluate_case(case)
            results.append(res)

        # Aggregate scores
        total = len(results)
        if total == 0:
            raise ValueError("Evaluation dataset is empty.")

        avg_stance_coverage = sum(r["scores"]["stance_coverage"] for r in results) / total
        avg_calibration = sum(r["scores"]["disagreement_calibration"] for r in results) / total
        avg_citation = sum(r["scores"]["citation_quality"] for r in results) / total
        avg_contradiction_accuracy = sum(r["contradiction_match"] for r in results) / total
        avg_latency = sum(r["latency_ms"] for r in results) / total

        scores = {
            "stance_coverage": avg_stance_coverage,
            "disagreement_calibration": avg_calibration,
            "citation_quality": avg_citation,
            "contradiction_accuracy": avg_contradiction_accuracy,
            "average_latency_ms": avg_latency
        }

        # Verify thresholds
        threshold_results = {}
        passed = True
        
        # Check stance coverage
        sc_thresh = self.mp_thresholds.get("stance_coverage", 4.0)
        sc_passed = avg_stance_coverage >= sc_thresh
        threshold_results["stance_coverage"] = {"score": avg_stance_coverage, "threshold": sc_thresh, "passed": sc_passed}
        if not sc_passed:
            passed = False

        # Check disagreement calibration
        dc_thresh = self.mp_thresholds.get("disagreement_calibration", 3.8)
        dc_passed = avg_calibration >= dc_thresh
        threshold_results["disagreement_calibration"] = {"score": avg_calibration, "threshold": dc_thresh, "passed": dc_passed}
        if not dc_passed:
            passed = False

        # Check citation quality
        cq_thresh = self.mp_thresholds.get("citation_quality", 4.0)
        cq_passed = avg_citation >= cq_thresh
        threshold_results["citation_quality"] = {"score": avg_citation, "threshold": cq_thresh, "passed": cq_passed}
        if not cq_passed:
            passed = False

        # Check contradiction accuracy
        ca_thresh = self.mp_thresholds.get("contradiction_accuracy", 0.8)
        ca_passed = avg_contradiction_accuracy >= ca_thresh
        threshold_results["contradiction_accuracy"] = {"score": avg_contradiction_accuracy, "threshold": ca_thresh, "passed": ca_passed}
        if not ca_passed:
            passed = False

        report = {
            "timestamp": datetime.now().isoformat(),
            "passed": passed,
            "aggregated_metrics": scores,
            "threshold_results": threshold_results,
            "case_details": results
        }

        # Save report
        os.makedirs(self.results_dir, exist_ok=True)
        out_file = os.path.join(self.results_dir, "multiperspective_eval_report.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Multi-Perspective evaluation run completed. Passed: {passed}. Report written to {out_file}")
        return report
