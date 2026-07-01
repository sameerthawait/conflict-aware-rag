import os
import sys
import logging
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from src.evaluation.evaluator import EvaluationReport
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.evaluation.ci_reporter")


class CIReporterError(Exception):
    """Raised when writing CI evaluation reports fails."""
    pass


class CIReporter:
    """Consolidates RAG evaluation runs into structured reports, writes to disk, and triggers CI shell exits."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        client: Optional[OpenAI] = None
    ) -> None:
        """Initializes the CIReporter.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            client: Optional OpenAI client.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.client = client

        eval_conf = config.get("evaluation", {})
        self.results_dir: str = eval_conf.get("results_output_path", "data/evaluation_results")

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.0)

    def _save_json_report(self, report: EvaluationReport) -> str:
        """Persists the evaluation report to disk as a JSON file.

        Args:
            report: The EvaluationReport object.

        Returns:
            The absolute path of the written file.

        Raises:
            CIReporterError: If directory creation or file writing fails.
        """
        try:
            os.makedirs(self.results_dir, exist_ok=True)
            report_path = os.path.join(self.results_dir, f"{report.run_id}.json")
            
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
            
            logger.info(f"Persisted evaluation run JSON report to: '{report_path}'")
            return report_path
        except Exception as e:
            error_msg = f"Failed to write evaluation report file to {self.results_dir}: {str(e)}"
            logger.error(error_msg)
            raise CIReporterError(error_msg) from e

    def _generate_failure_report(self, report: EvaluationReport) -> str:
        """Invokes the failure reporter LLM prompt to summarize errors.

        Args:
            report: The EvaluationReport object.

        Returns:
            The markdown-formatted failure report string.
        """
        if not self.client:
            logger.warning("No LLM client configured for CIReporter. Returning basic fallback text.")
            return "CI failure report bypassed due to missing client configuration."

        # 1. Format failed thresholds details
        failed_thresholds = []
        for metric, res in report.threshold_results.items():
            if not res["passed"]:
                failed_thresholds.append(
                    f"- Metric: '{metric}' | Score: {res['score']:.2f} (Threshold required: {res['threshold']:.2f})"
                )
        failed_thresholds_details = "\n".join(failed_thresholds)

        # 2. Format failing cases details
        failing_cases = []
        for case in report.failed_cases[:10]:  # Limit to top 10 failing cases to fit context limits
            failing_cases.append(
                f"Case ID: {case['id']} | Type: {case['type']}\n"
                f"Query: {case['query']}\n"
                f"Expected: {case['expected_answer']}\n"
                f"Generated Answer: {case['generated_answer']}\n"
                f"Scores: Faithfulness={case['scores']['faithfulness']}, Correctness={case['scores']['correctness']}, "
                f"Completeness={case['scores']['completeness']}, Citation={case['scores']['citation_quality']}\n"
                f"Overall Score: {case['overall_score']:.2f}\n"
                f"Failed Dimensions: {', '.join(case['failed_dimensions'])}\n"
                f"Reasoning: {case['scores']['reasoning']}\n"
                f"---"
            )
        failing_cases_details = "\n".join(failing_cases)

        try:
            prompt = self.prompt_manager.get_prompt(
                "ci_failure_report_generator",
                failed_thresholds_details=failed_thresholds_details,
                failing_cases_details=failing_cases_details
            )

            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.config.get("llm", {}).get("max_tokens_to_sample", 1024)
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Failed to generate failure report via LLM: {str(e)}")
            return (
                f"=== LLM Failure Report Generation Failed ===\n"
                f"Failed Metrics:\n{failed_thresholds_details}\n"
                f"Total Failing Cases: {len(report.failed_cases)}"
            )

    def report(self, report: EvaluationReport) -> None:
        """Saves run details, prints output summaries to standard output, and exits the shell process.

        Args:
            report: EvaluationReport instance.
        """
        # Save run results to disk
        try:
            report_file = self._save_json_report(report)
        except Exception as e:
            report_file = f"Failed to save ({str(e)})"

        # Print overall metrics summary
        print(f"\n==================================================")
        print(f"RAG EVALUATION RUN SUMMARY | ID: {report.run_id}")
        print(f"Timestamp: {report.timestamp}")
        print(f"Report File: {report_file}")
        print(f"==================================================")

        for metric, res in report.threshold_results.items():
            status_indicator = "PASS" if res["passed"] else "FAIL"
            print(f"- {metric.upper():<20} : Score: {res['score']:.2f} (Threshold: {res['threshold']:.2f}) -> [{status_indicator}]")

        print(f"Total Failing Cases: {len(report.failed_cases)}")
        print(f"==================================================")

        if report.passed:
            # Print green success summary and exit 0
            green_success = (
                f"\033[92m"  # Green text ANSI start
                f"==================================================\n"
                f"✔ SUCCESS: RAG SYSTEM PASSED ALL CI EVALUATION THRESHOLDS\n"
                f"=================================================="
                f"\033[0m"   # ANSI end
            )
            print(green_success)
            sys.exit(0)
        else:
            # Print red warning header
            red_failure_header = (
                f"\033[91m"  # Red text ANSI start
                f"==================================================\n"
                f"✖ FAILURE: RAG SYSTEM FAILED QUALITY EVALUATION THRESHOLDS\n"
                f"=================================================="
                f"\033[0m"   # ANSI end
            )
            print(red_failure_header)

            # Generate and print the LLM failure report
            failure_report = self._generate_failure_report(report)
            print(failure_report)
            print(f"==================================================")
            
            sys.exit(1)
