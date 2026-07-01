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
from src.evaluation.dataset_generator import GoldenDatasetGenerator


def setup_args() -> argparse.ArgumentParser:
    """Sets up CLI arguments for the dataset generator script."""
    parser = argparse.ArgumentParser(
        description="Generates a synthetic RAG evaluation Q&A dataset from indexed ChromaDB document chunks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=100,
        help="Maximum number of document chunks to fetch and generate QA pairs for."
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Custom path to save the generated JSONL dataset. Defaults to the path configured in config.yaml."
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

    # Initialize Chroma vector store
    try:
        vector_store = ChromaVectorStore(config)
        vector_store.initialize()
    except Exception as e:
        print(f"Error initializing Chroma vector store connection: {str(e)}", file=sys.stderr)
        sys.exit(1)

    # Execute generator
    try:
        generator = GoldenDatasetGenerator(
            config=config,
            prompt_manager=prompt_manager,
            vector_store=vector_store
        )
        
        output_file = generator.generate(
            max_chunks=args.max_chunks,
            output_file=args.output_path
        )
        
        # Print human review instructions
        print(f"\n==================================================")
        print(f"SYNTHETIC DATASET GENERATION COMPLETED")
        print(f"Dataset path: {output_file}")
        print(f"==================================================")
        print(f"Instructions for Human Review Process:")
        print(f"1. Open the output file in a text editor.")
        print(f"2. Inspect each generated QA pair (type, question, expected_answer).")
        print(f"3. Refine any spelling or factual issues to match exact context facts.")
        print(f"4. Change the 'human_verified' field from false to true.")
        print(f"5. Save the file. Verified questions are now ready for automated CI testing!")
        print(f"==================================================")

    except Exception as e:
        print(f"Dataset generation failed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
