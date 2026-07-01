import os
import time
import logging
import json
import uuid
import re
import yaml
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from openai import OpenAI

from src.generation.pipeline import RAGPipeline, RAGResponse
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.evaluation.evaluator")


class EvaluationError(Exception):
    """Raised when RAG evaluation executions fail."""
    pass


class EvaluationReport:
    """Encapsulates the aggregated metrics and failing cases from an evaluation run."""

    def __init__(
        self,
        scores_per_dimension: Dict[str, float],
        threshold_results: Dict[str, Dict[str, Any]],
        failed_cases: List[Dict[str, Any]],
        passed: bool,
        run_id: str,
        timestamp: str
    ) -> None:
        """Initializes the EvaluationReport.

        Args:
            scores_per_dimension: Dict of average scores per metric.
            threshold_results: Dict of metric pass status and thresholds.
            failed_cases: List of cases that failed any metric threshold.
            passed: Overall pass status of the evaluation run.
            run_id: Unique run ID string.
            timestamp: ISO timestamp string.
        """
        self.scores_per_dimension = scores_per_dimension
        self.threshold_results = threshold_results
        self.failed_cases = failed_cases
        self.passed = passed
        self.run_id = run_id
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Converts the evaluation report to a dictionary structure."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "scores_per_dimension": self.scores_per_dimension,
            "threshold_results": self.threshold_results,
            "failed_cases": self.failed_cases
        }


class RAGEvaluator:
    """Runs automated evaluation on RAG queries against ground truth datasets using LLM-as-a-judge scoring."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        pipeline: RAGPipeline,
        client: Optional[OpenAI] = None
    ) -> None:
        """Initializes the RAGEvaluator.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            pipeline: Initialized RAGPipeline instance.
            client: Optional OpenAI client.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.pipeline = pipeline

        if client is not None:
            self.client = client
        else:
            self.client = pipeline.client

        # Load evaluation parameters and thresholds
        eval_conf = config.get("evaluation", {})
        self.dataset_path: str = eval_conf.get("golden_dataset_path", "data/golden_dataset/qa_pairs.json")
        self.results_dir: str = eval_conf.get("results_output_path", "data/evaluation_results")
        
        # Default thresholds
        self.thresholds: Dict[str, float] = eval_conf.get("thresholds", {
            "overall_score": 3.8,
            "faithfulness": 4.0,
            "correctness": 3.5,
            "completeness": 3.5,
            "citation_quality": 4.0,
            "refusal_accuracy": 0.9
        })

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.0)

        # Config refusal message for checking refusal accuracy
        self.refusal_message: str = config.get("quality_gates", {}).get(
            "refusal_message",
            "I am sorry, but I could not find any relevant information in the provided context to answer your query."
        ).strip()

    def _parse_evaluator_response(self, text: str) -> Dict[str, Any]:
        """Parses metric scores and boolean values from the evaluator prompt completion.

        Args:
            text: Raw string completion response from LLM.

        Returns:
            Dict containing faithfulness, correctness, completeness, citation_quality, and refused values.
        """
        # Default fallback dictionary
        parsed_scores = {
            "faithfulness": 1.0,
            "correctness": 1.0,
            "completeness": 1.0,
            "citation_quality": 1.0,
            "refused": False,
            "reasoning": "Failed to parse response."
        }

        try:
            parsed = yaml.safe_load(text)
            if isinstance(parsed, dict):
                for k in ["faithfulness", "correctness", "completeness", "citation_quality"]:
                    if k in parsed:
                        parsed_scores[k] = min(max(float(parsed[k]), 1.0), 5.0)
                if "refused" in parsed:
                    val = parsed["refused"]
                    parsed_scores["refused"] = str(val).lower() == "true"
                if "reasoning" in parsed:
                    parsed_scores["reasoning"] = str(parsed["reasoning"])
                return parsed_scores
        except Exception as e:
            logger.warning(f"YAML parsing of faithfulness response failed: {str(e)}. Falling back to regex.")

        # Regex Fallbacks
        f_match = re.search(r"faithfulness.*?:?\s*(\d+(\.\d+)?)", text, re.IGNORECASE)
        corr_match = re.search(r"correctness.*?:?\s*(\d+(\.\d+)?)", text, re.IGNORECASE)
        comp_match = re.search(r"completeness.*?:?\s*(\d+(\.\d+)?)", text, re.IGNORECASE)
        cit_match = re.search(r"citation_quality.*?:?\s*(\d+(\.\d+)?)", text, re.IGNORECASE)
        ref_match = re.search(r"refused.*?:?\s*(true|false)", text, re.IGNORECASE)
        reason_match = re.search(r"reasoning.*?:?\s*\"?([^\n\"]+)\"?", text, re.IGNORECASE)


        if f_match:
            parsed_scores["faithfulness"] = min(max(float(f_match.group(1)), 1.0), 5.0)
        if corr_match:
            parsed_scores["correctness"] = min(max(float(corr_match.group(1)), 1.0), 5.0)
        if comp_match:
            parsed_scores["completeness"] = min(max(float(comp_match.group(1)), 1.0), 5.0)
        if cit_match:
            parsed_scores["citation_quality"] = min(max(float(cit_match.group(1)), 1.0), 5.0)
        if ref_match:
            parsed_scores["refused"] = ref_match.group(1).lower() == "true"
        if reason_match:
            parsed_scores["reasoning"] = reason_match.group(1).strip()

        return parsed_scores

    def _evaluate_case(self, query: str, context: str, expected_answer: str, generated_answer: str) -> Dict[str, Any]:
        """Invokes the evaluator LLM to score the generated output.

        Args:
            query: Question asked.
            context: Retrieved context snippets.
            expected_answer: Ground truth answer.
            generated_answer: Actual RAG generated output.

        Returns:
            Dict containing dimension scores.
        """
        if not self.client:
            logger.warning("No LLM client configured for RAGEvaluator. Returning lowest scores.")
            return {
                "faithfulness": 1.0,
                "correctness": 1.0,
                "completeness": 1.0,
                "citation_quality": 1.0,
                "refused": False,
                "reasoning": "Bypassed."
            }

        try:
            # Format evaluation prompt
            prompt = self.prompt_manager.get_prompt(
                "faithfulness_evaluator",
                query=query,
                context=context,
                expected_answer=expected_answer,
                generated_answer=generated_answer
            )

            # Call LLM
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.config.get("llm", {}).get("max_tokens_to_sample", 1024)
            )
            response_text = response.choices[0].message.content

            return self._parse_evaluator_response(response_text)

        except Exception as e:
            logger.error(f"Failed to evaluate case: {str(e)}")
            return {
                "faithfulness": 1.0,
                "correctness": 1.0,
                "completeness": 1.0,
                "citation_quality": 1.0,
                "refused": False,
                "reasoning": f"Evaluation error: {str(e)}"
            }

    def run_evaluation(
        self,
        dataset_path: Optional[str] = None,
        threshold_override: Optional[Dict[str, float]] = None
    ) -> EvaluationReport:
        """Loads human-verified QA pairs, runs pipeline query queries, and evaluates outcomes against thresholds.

        Args:
            dataset_path: Optional path to override default dataset source file.
            threshold_override: Dict to temporarily override metric thresholds locally.

        Returns:
            An EvaluationReport.

        Raises:
            EvaluationError: If dataset loading or processing fails.
        """
        run_id = f"eval_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat() + "Z"

        if not dataset_path:
            dataset_path = self.dataset_path

        active_thresholds = self.thresholds.copy()
        if threshold_override:
            active_thresholds.update(threshold_override)

        logger.info(f"Starting evaluation run {run_id} using dataset: '{dataset_path}'")

        # 1. Load dataset (JSONL format)
        if not os.path.exists(dataset_path):
            raise EvaluationError(f"Golden dataset file not found at path: {dataset_path}")

        qa_pairs: List[Dict[str, Any]] = []
        try:
            with open(dataset_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        qa_pairs.append(json.loads(line))
        except Exception as e:
            raise EvaluationError(f"Failed to load and parse JSONL dataset file: {str(e)}") from e

        # Filter human_verified = True only
        verified_pairs = [qa for qa in qa_pairs if qa.get("human_verified", False)]
        if not verified_pairs:
            logger.warning("No human_verified = true QA pairs found. Proceeding with all QA pairs to avoid blocking.")
            verified_pairs = qa_pairs

        if not verified_pairs:
            raise EvaluationError("The evaluation dataset has zero QA pair records.")

        logger.info(f"Loaded {len(verified_pairs)} verified QA pairs for test run.")

        # Metric tracking lists
        faithfulness_scores = []
        correctness_scores = []
        completeness_scores = []
        citation_scores = []
        
        refusal_correct_count = 0
        refusal_total_cases = 0

        failed_cases: List[Dict[str, Any]] = []

        # 2. Iterate each Q&A pair and query pipeline
        for idx, qa in enumerate(verified_pairs):
            query = qa["question"]
            expected = qa["expected_answer"]
            q_id = qa.get("id", f"qa_{idx+1}")
            q_type = qa.get("type", "DIRECT")

            logger.info(f"Evaluating case {idx+1}/{len(verified_pairs)} | ID: {q_id} | Type: {q_type}")

            try:
                # Query the RAG Pipeline
                pipeline_resp: RAGResponse = self.pipeline.run_pipeline(query)
                generated_ans = pipeline_resp.answer
                
                # Fetch retrieved context content
                # Retrieve the actual search results using retriever to format the evaluated context
                retrieved_chunks, _ = self.pipeline.hybrid_retriever.retrieve(query)
                formatted_context = "\n---\n".join([c.text for c in retrieved_chunks])
            except Exception as e:
                logger.error(f"RAG Pipeline failed for query '{query}': {str(e)}")
                generated_ans = "Pipeline Error"
                formatted_context = ""

            # Evaluate metrics via LLM judge
            scores = self._evaluate_case(query, formatted_context, expected, generated_ans)

            # Record scores
            faithfulness_scores.append(scores["faithfulness"])
            correctness_scores.append(scores["correctness"])
            completeness_scores.append(scores["completeness"])
            citation_scores.append(scores["citation_quality"])

            # Refusal logic check
            is_refusal_case = (expected.strip() == self.refusal_message)
            actual_refused = scores["refused"] or (generated_ans.strip() == self.refusal_message)
            
            # Record refusal correctness
            refusal_correct = (is_refusal_case == actual_refused)
            if refusal_correct:
                refusal_correct_count += 1
            refusal_total_cases += 1

            # Check if this specific case failed any individual dimension threshold
            case_failed = False
            case_failures = []
            
            overall_val = (scores["faithfulness"] + scores["correctness"] + scores["completeness"] + scores["citation_quality"]) / 4.0

            if scores["faithfulness"] < active_thresholds.get("faithfulness", 4.0):
                case_failed = True
                case_failures.append("faithfulness")
            if scores["correctness"] < active_thresholds.get("correctness", 3.5):
                case_failed = True
                case_failures.append("correctness")
            if scores["completeness"] < active_thresholds.get("completeness", 3.5):
                case_failed = True
                case_failures.append("completeness")
            if scores["citation_quality"] < active_thresholds.get("citation_quality", 4.0):
                case_failed = True
                case_failures.append("citation_quality")
            if overall_val < active_thresholds.get("overall_score", 3.8):
                case_failed = True
                case_failures.append("overall_score")
            if is_refusal_case and not actual_refused:
                case_failed = True
                case_failures.append("refusal_accuracy")

            if case_failed:
                failed_cases.append({
                    "id": q_id,
                    "type": q_type,
                    "query": query,
                    "expected_answer": expected,
                    "generated_answer": generated_ans,
                    "scores": scores,
                    "overall_score": overall_val,
                    "failed_dimensions": case_failures
                })

        # 3. Compute Aggregates
        total_cases = len(verified_pairs)
        avg_faithfulness = sum(faithfulness_scores) / total_cases
        avg_correctness = sum(correctness_scores) / total_cases
        avg_completeness = sum(completeness_scores) / total_cases
        avg_citation = sum(citation_scores) / total_cases
        
        avg_overall = (avg_faithfulness + avg_correctness + avg_completeness + avg_citation) / 4.0
        refusal_accuracy_val = refusal_correct_count / refusal_total_cases if refusal_total_cases > 0 else 1.0

        scores_per_dimension = {
            "faithfulness": avg_faithfulness,
            "correctness": avg_correctness,
            "completeness": avg_completeness,
            "citation_quality": avg_citation,
            "overall_score": avg_overall,
            "refusal_accuracy": refusal_accuracy_val
        }

        # 4. Check against thresholds
        threshold_results = {}
        passed = True

        for metric, val in scores_per_dimension.items():
            threshold_val = active_thresholds.get(metric, 0.0)
            metric_passed = val >= threshold_val
            if not metric_passed:
                passed = False
            threshold_results[metric] = {
                "score": val,
                "threshold": threshold_val,
                "passed": metric_passed
            }

        report = EvaluationReport(
            scores_per_dimension=scores_per_dimension,
            threshold_results=threshold_results,
            failed_cases=failed_cases,
            passed=passed,
            run_id=run_id,
            timestamp=timestamp
        )

        logger.info(f"Evaluation run {run_id} completed. Passed: {passed}.")
        return report
