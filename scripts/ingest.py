from dotenv import load_dotenv
load_dotenv()
import os
import argparse
import logging
from typing import Dict, Any, List
from openai import OpenAI
from src.utils.config_loader import load_config
from src.utils.prompt_manager import PromptManager
from src.utils.secret_loader import get_secret
from src.ingestion.document_loader import DocumentLoader
from src.ingestion.chunker import SemanticChunker
from src.ingestion.vector_store import ChromaVectorStore
from src.ingestion.pipeline import IngestionPipeline, IngestionResult

# Configure CLI logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
from src.utils.secret_masker import install_secret_masker
install_secret_masker()
logger = logging.getLogger("rag_system.cli.ingest")

DEFAULT_PATH = os.getenv("INGEST_PATH", "./data/raw")


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments.

    Returns:
        The parsed Namespace containing argument fields.
    """
    parser = argparse.ArgumentParser(description="Ingest documents into the production RAG system.")
    parser.add_argument(
        "--path",
        type=str,
        default=DEFAULT_PATH,
        help="Path to the file or directory to ingest."
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=False,
        help="Recursively ingest subdirectories (only applies if --path is a directory)."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to the config.yaml file."
    )
    parser.add_argument(
        "--prompts",
        type=str,
        default="prompts/prompts.yaml",
        help="Path to the prompts.yaml file."
    )
    return parser.parse_args()


def print_summary_table(result: IngestionResult) -> None:
    """Prints a formatted summary table to console.

    Args:
        result: IngestionResult containing run metrics.
    """
    print("\n" + "=" * 55)
    print(f"{'INGESTION PIPELINE RUN SUMMARY':^55}")
    print("=" * 55)
    print(f" {'Metric':<30} | {'Value':<20}")
    print("-" * 55)
    print(f" {'Successful Ingestions':<30} | {len(result.indexed_documents):<20}")
    print(f" {'Skipped (Duplicates)':<30} | {len(result.skipped_documents):<20}")
    print(f" {'Total database chunks added':<30} | {result.total_chunks:<20}")
    print(f" {'Errors encountered':<30} | {len(result.errors):<20}")
    print("=" * 55)

    if result.errors:
        print("\nERRORS ENCOUNTERED:")
        for path, error in result.errors.items():
            print(f"- {path}: {error}")
        print("=" * 55)


def main() -> None:
    """CLI execution entrypoint."""
    args = parse_arguments()

    if not os.path.exists(args.path):
        logger.error(f"Provided path does not exist: {args.path}")
        print(f"Error: Path '{args.path}' does not exist.")
        return

    # Load configurations
    try:
        config = load_config(args.config)
        # Update logger level to match config
        log_level_str = config.get("system", {}).get("log_level", "INFO").upper()
        logging.getLogger("rag_system").setLevel(getattr(logging, log_level_str, logging.INFO))
    except Exception as e:
        logger.critical(f"Initialization failure during config load: {str(e)}")
        print(f"Error loading system configuration: {str(e)}")
        return

    # Initialize components
    logger.info("Initializing system components...")
    try:
        prompt_manager = PromptManager(prompts_path=args.prompts)
        doc_loader = DocumentLoader()
        chunker = SemanticChunker(config=config, prompt_manager=prompt_manager)
        vector_store = ChromaVectorStore(config=config)
        vector_store.initialize()

        # Check for NVIDIA API client setup
        api_key = get_secret("NVIDIA_API_KEY", fallback_env_name="NVIDIA_NIM_API_KEY")
        client = None
        if api_key:
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=api_key
            )
        else:
            logger.warning("No NVIDIA API key found. Summarization will be skipped.")

        pipeline = IngestionPipeline(
            config=config,
            doc_loader=doc_loader,
            chunker=chunker,
            vector_store=vector_store,
            client=client
        )
    except Exception as e:
        logger.critical(f"Failed to initialize components: {str(e)}")
        print(f"Component initialization error: {str(e)}")
        return

    # Execute ingestion
    logger.info(f"Beginning ingestion for path: {args.path}")
    if os.path.isdir(args.path):
        result = pipeline.ingest_directory(args.path, recursive=args.recursive)
    else:
        result = pipeline.ingest_file(args.path)

    # Print summary table
    print_summary_table(result)


if __name__ == "__main__":
    main()
