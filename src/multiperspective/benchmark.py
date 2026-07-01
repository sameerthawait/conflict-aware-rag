import os
import json
import logging
from typing import List, Dict, Any, Tuple, Optional

from src.ingestion.vector_store import SearchResult
from src.multiperspective.contradiction_detector import ContradictionDetector, ContradictionResult

logger = logging.getLogger("rag_system.multiperspective.benchmark")


class BenchmarkCase:
    """Represents a single test case for the contradiction benchmark."""

    def __init__(
        self,
        case_id: str,
        chunk_a: str,
        source_a: str,
        chunk_b: str,
        source_b: str,
        ground_truth: bool,
        contradiction_type: Optional[str],
        difficulty: str,
        notes: str
    ) -> None:
        self.case_id = case_id
        self.chunk_a = chunk_a
        self.source_a = source_a
        self.chunk_b = chunk_b
        self.source_b = source_b
        self.ground_truth = ground_truth
        self.contradiction_type = contradiction_type
        self.difficulty = difficulty
        self.notes = notes


class BenchmarkResult:
    """Detailed results of running a contradiction detection benchmark."""

    def __init__(
        self,
        total_cases: int,
        tp: int,
        fp: int,
        tn: int,
        fn: int,
        precision: float,
        recall: float,
        f1: float,
        false_positive_rate: float,
        llm_call_count: int,
        pre_filtered_count: int,
        type_metrics: Dict[str, Dict[str, float]]
    ) -> None:
        self.total_cases = total_cases
        self.tp = tp
        self.fp = fp
        self.tn = tn
        self.fn = fn
        self.precision = precision
        self.recall = recall
        self.f1 = f1
        self.false_positive_rate = false_positive_rate
        self.llm_call_count = llm_call_count
        self.pre_filtered_count = pre_filtered_count
        self.type_metrics = type_metrics


class ContradictionBenchmark:
    """Runs evaluations against contradiction pairs to measure detection precision, recall, and pre-filtering rates."""

    def __init__(self, benchmark_path: str) -> None:
        self.benchmark_path = benchmark_path

    def load_benchmark(self) -> List[BenchmarkCase]:
        """Loads and parses benchmark JSON test cases."""
        if not os.path.exists(self.benchmark_path):
            raise FileNotFoundError(f"Benchmark file not found at path: {self.benchmark_path}")
            
        with open(self.benchmark_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cases = []
        for item in data:
            cases.append(BenchmarkCase(
                case_id=item.get("id"),
                chunk_a=item.get("chunk_a"),
                source_a=item.get("source_a", "Doc A"),
                chunk_b=item.get("chunk_b"),
                source_b=item.get("source_b", "Doc B"),
                ground_truth=bool(item.get("ground_truth", False)),
                contradiction_type=item.get("contradiction_type"),
                difficulty=item.get("difficulty", "medium"),
                notes=item.get("notes", "")
            ))
        return cases

    def run(self, detector: ContradictionDetector) -> BenchmarkResult:
        """Executes contradiction detection against loaded benchmark cases."""
        cases = self.load_benchmark()
        
        tp = fp = tn = fn = 0
        llm_calls = 0
        pre_filtered = 0
        
        # Track metrics grouped by contradiction category
        type_counts: Dict[str, Dict[str, int]] = {}

        for case in cases:
            # Wrap raw string passages into SearchResult structures matching detector API
            s_a = SearchResult(
                chunk_id=f"{case.case_id}_a",
                text=case.chunk_a,
                score=0.5, # Mid similarity to allow LLM checks
                metadata={"title": case.source_a}
            )
            s_b = SearchResult(
                chunk_id=f"{case.case_id}_b",
                text=case.chunk_b,
                score=0.5,
                metadata={"title": case.source_b}
            )

            # Evaluate pair
            res: ContradictionResult = detector.detect_pairwise(s_a, s_b, query="General Query")

            # Check if it was pre-filtered
            if "threshold" in res.explanation or "duplicates" in res.explanation or "shift" in res.explanation:
                pre_filtered += 1
            else:
                llm_calls += 1

            # Assert outcomes
            predicted = res.is_contradiction
            actual = case.ground_truth
            
            c_type = case.contradiction_type or "none"
            type_counts.setdefault(c_type, {"tp": 0, "fp": 0, "tn": 0, "fn": 0})

            if predicted and actual:
                tp += 1
                type_counts[c_type]["tp"] += 1
            elif predicted and not actual:
                fp += 1
                type_counts[c_type]["fp"] += 1
            elif not predicted and not actual:
                tn += 1
                type_counts[c_type]["tn"] += 1
            elif not predicted and actual:
                fn += 1
                type_counts[c_type]["fn"] += 1

        # Calculate metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        # Calculate category specific metrics
        type_metrics: Dict[str, Dict[str, float]] = {}
        for t, counts in type_counts.items():
            ctp, cfp, ctn, cfn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
            c_prec = ctp / (ctp + cfp) if (ctp + cfp) > 0 else 0.0
            c_rec = ctp / (ctp + cfn) if (ctp + cfn) > 0 else 0.0
            c_f1 = 2 * c_prec * c_rec / (c_prec + c_rec) if (c_prec + c_rec) > 0 else 0.0
            type_metrics[t] = {
                "precision": c_prec,
                "recall": c_rec,
                "f1": c_f1
            }

        return BenchmarkResult(
            total_cases=len(cases),
            tp=tp,
            fp=fp,
            tn=tn,
            fn=fn,
            precision=precision,
            recall=recall,
            f1=f1,
            false_positive_rate=fpr,
            llm_call_count=llm_calls,
            pre_filtered_count=pre_filtered,
            type_metrics=type_metrics
        )

    def report(self, res: BenchmarkResult) -> str:
        """Formats evaluation metrics into a clean markdown report."""
        llm_efficiency_pct = (res.pre_filtered_count / res.total_cases) * 100 if res.total_cases > 0 else 0.0
        
        lines = [
            "# Contradiction Detection Pipeline Evaluation Report",
            "",
            "## Summary Metrics",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| **Total Evaluated Cases** | {res.total_cases} |",
            f"| **True Positives (TP)** | {res.tp} |",
            f"| **False Positives (FP)** | {res.fp} |",
            f"| **True Negatives (TN)** | {res.tn} |",
            f"| **False Negatives (FN)** | {res.fn} |",
            f"| **Precision** | {res.precision:.4f} |",
            f"| **Recall** | {res.recall:.4f} |",
            f"| **F1 Score** | {res.f1:.4f} |",
            f"| **False Positive Rate (FPR)** | {res.false_positive_rate:.4f} |",
            "",
            "## Pre-filtering Efficiency",
            f"- **Obvious Pairs Pre-filtered (Embedding cosine)**: {res.pre_filtered_count} ({llm_efficiency_pct:.1f}%)",
            f"- **Pairs Forwarded to LLM**: {res.llm_call_count}",
            "",
            "## Performance by Contradiction Category",
            "| Category | Precision | Recall | F1 Score |",
            "| :--- | :--- | :--- | :--- |"
        ]

        for category, metrics in res.type_metrics.items():
            if category == "none":
                continue
            lines.append(
                f"| {category.capitalize()} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['f1']:.4f} |"
            )
            
        return "\n".join(lines)
