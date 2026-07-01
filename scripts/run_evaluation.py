#!/usr/bin/env python
from dotenv import load_dotenv
load_dotenv()
import argparse
import sys
import os
import logging
from typing import Dict, Any

# Ensure root directory is on PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.config_loader import load_config
from src.utils.prompt_manager import PromptManager
from src.ingestion.vector_store import ChromaVectorStore
from src.generation.pipeline import RAGPipeline
from src.evaluation.evaluator import RAGEvaluator
from src.evaluation.ci_reporter import CIReporter


def parse_threshold_override(arg_str: str) -> Dict[str, float]:
    """Parses comma-separated key=value threshold strings into float dictionaries.

    Example: "faithfulness=4.2,correctness=3.8" -> {"faithfulness": 4.2, "correctness": 3.8}
    """
    overrides = {}
    if not arg_str:
        return overrides
    
    parts = arg_str.split(",")
    for part in parts:
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        try:
            overrides[k.strip().lower()] = float(v.strip())
        except ValueError:
            print(f"Warning: Ignored invalid threshold override value for {k}: {v}", file=sys.stderr)
    return overrides


def setup_args() -> argparse.ArgumentParser:
    """Sets up CLI arguments for the evaluation script."""
    parser = argparse.ArgumentParser(
        description="Runs RAG evaluation pipeline against a golden dataset, scores results, and reports outcomes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to the JSONL golden dataset file. Defaults to path configured in config.yaml."
    )
    parser.add_argument(
        "--threshold-override",
        type=str,
        default="",
        help="Comma-separated overrides for quality metrics. Example: 'overall_score=4.0,faithfulness=4.5'"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level to use during execution."
    )
    return parser


def main() -> None:
    """CLI execution entrypoint."""
    parser = setup_args()
    args = parser.parse_args()

    # Initialize logging
    logging.basicConfig(level=getattr(logging, args.log_level))

    # Parse threshold overrides
    threshold_overrides = parse_threshold_override(args.threshold_override)

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        print(f"Error loading system configuration: {str(e)}", file=sys.stderr)
        sys.exit(1)

    # Initialize prompt manager
    try:
        prompt_manager = PromptManager()
    except Exception as e:
        print(f"Error loading prompt configurations: {str(e)}", file=sys.stderr)
        sys.exit(1)

    # Initialize Chroma vector store connection
    try:
        vector_store = ChromaVectorStore(config)
        vector_store.initialize()
    except Exception as e:
        print(f"Error initializing Chroma vector store connection: {str(e)}", file=sys.stderr)
        sys.exit(1)

    # Initialize RAG Pipeline
    try:
        pipeline = RAGPipeline(
            config=config,
            prompt_manager=prompt_manager,
            vector_store=vector_store
        )
    except Exception as e:
        print(f"Error initializing RAG pipeline coordinator: {str(e)}", file=sys.stderr)
        sys.exit(1)

    # Run evaluation
    try:
        evaluator = RAGEvaluator(
            config=config,
            prompt_manager=prompt_manager,
            pipeline=pipeline
        )
        
        report = evaluator.run_evaluation(
            dataset_path=args.dataset,
            threshold_override=threshold_overrides
        )
        
        # Report results and manage CI exit
        reporter = CIReporter(
            config=config,
            prompt_manager=prompt_manager,
            client=pipeline.client
        )
        reporter.report(report)

    except Exception as e:
        print(f"Evaluation runner execution failed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
