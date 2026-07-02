import os
import time
import logging
import json
import re
import yaml
from typing import Dict, List, Any, Optional, Tuple
from openai import OpenAI
from src.utils.secret_loader import get_secret
from src.ingestion.vector_store import ChromaVectorStore
from src.utils.prompt_manager import PromptManager

# Initialize structured logging
logger = logging.getLogger("rag_system.evaluation.dataset_generator")


class DatasetGeneratorError(Exception):
    """Raised when generating the golden evaluation dataset fails."""
    pass


class GoldenDatasetGenerator:
    """Iterates through database chunks to generate synthetic evaluation QA pairs via LLM analysis."""

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        vector_store: ChromaVectorStore,
        client: Optional[OpenAI] = None
    ) -> None:
        """Initializes the GoldenDatasetGenerator.

        Args:
            config: System configuration dictionary.
            prompt_manager: PromptManager instance.
            vector_store: Initialized ChromaVectorStore.
            client: Optional pre-configured OpenAI client.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.vector_store = vector_store
        
        if client is not None:
            self.client = client
        else:
            api_key = get_secret("NVIDIA_API_KEY", fallback_env_name="NVIDIA_NIM_API_KEY")
            if not api_key:
                raise RuntimeError("NVIDIA API authentication key (NVIDIA_API_KEY or NVIDIA_NIM_API_KEY) is missing. Unable to initialize GoldenDatasetGenerator LLM client.")
            base_url = config.get("llm", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
            self.client = OpenAI(base_url=base_url, api_key=api_key)

        llm_conf = config.get("llm", {})
        self.llm_model: str = llm_conf.get("model_name", "meta/llama-3.1-70b-instruct")
        self.temperature: float = llm_conf.get("temperature", 0.5)  # Slightly higher temp for synthetic creativity

        eval_conf = config.get("evaluation", {})
        self.default_output_path: str = eval_conf.get("golden_dataset_path", "data/golden_dataset/qa_pairs.json")

    def _parse_llm_response(self, text: str) -> Tuple[str, str, str, str]:
        """Parses TYPE, QUESTION, EXPECTED_ANSWER, and DIFFICULTY from YAML LLM response.

        Args:
            text: Raw string completion response from LLM.

        Returns:
            Tuple of (type, question, expected_answer, difficulty).
        """
        q_type = "DIRECT"
        question = ""
        expected_answer = ""
        difficulty = "Medium"

        try:
            parsed = yaml.safe_load(text)
            if isinstance(parsed, dict):
                q_type = str(parsed.get("TYPE", "DIRECT")).upper().strip()
                question = str(parsed.get("QUESTION", "")).strip()
                expected_answer = str(parsed.get("EXPECTED_ANSWER", "")).strip()
                difficulty = str(parsed.get("DIFFICULTY", "Medium")).strip()
                return q_type, question, expected_answer, difficulty
        except Exception as e:
            logger.warning(f"YAML parsing of generated QA pair failed: {str(e)}. Falling back to regex.")

        # Regex Fallbacks
        type_match = re.search(r"TYPE:\s*\"?(DIRECT|REASONING|BOUNDARY)\"?", text, re.IGNORECASE)
        quest_match = re.search(r"QUESTION:\s*\"?([^\n\"]+)\"?", text, re.IGNORECASE)
        ans_match = re.search(r"EXPECTED_ANSWER:\s*\"?([^\n\"]+)\"?", text, re.IGNORECASE)
        diff_match = re.search(r"DIFFICULTY:\s*\"?(Easy|Medium|Hard)\"?", text, re.IGNORECASE)

        if type_match:
            q_type = type_match.group(1).upper()
        if quest_match:
            question = quest_match.group(1).strip()
        if ans_match:
            expected_answer = ans_match.group(1).strip()
        if diff_match:
            difficulty = diff_match.group(1).strip()

        return q_type, question, expected_answer, difficulty

    def generate(self, max_chunks: int = 100, output_file: Optional[str] = None) -> str:
        """Downloads all active vector store chunks and calls the LLM to generate synthetic evaluation QAs.

        Args:
            max_chunks: Upper limit of database chunks to analyze.
            output_file: Optional custom JSONL output file path.

        Returns:
            Path of the generated dataset file.

        Raises:
            DatasetGeneratorError: If database query or file saving operations fail.
        """
        logger.info(f"Initiating synthetic QA dataset generation (max_chunks={max_chunks})...")
        start_time = time.perf_counter()

        if not output_file:
            output_file = self.default_output_path

        # 1. Fetch document chunks from database
        try:
            self.vector_store._ensure_initialized()
            assert self.vector_store.collection is not None
            results = self.vector_store.collection.get(include=["documents"])
        except Exception as e:
            raise DatasetGeneratorError(f"Failed to retrieve chunks from ChromaDB: {str(e)}") from e

        ids = results.get("ids", [])
        docs = results.get("documents", [])

        if not ids:
            logger.warning("No records found in ChromaDB collection. Cannot generate dataset.")
            return output_file

        # Slice to max chunks
        chunk_pairs = list(zip(ids, docs))[:max_chunks]
        logger.info(f"Retrieved {len(chunk_pairs)} candidate chunks from database.")

        qa_pairs: List[Dict[str, Any]] = []
        question_types = ["DIRECT", "REASONING", "BOUNDARY"]

        # 2. Iterate and generate QA pair for each chunk
        for idx, (chunk_id, doc_text) in enumerate(chunk_pairs):
            q_type = question_types[idx % len(question_types)]
            logger.info(f"Generating synthetic QA pair {idx+1}/{len(chunk_pairs)} (Type: {q_type}) for chunk {chunk_id}")

            try:
                # Format prompts
                prompt = self.prompt_manager.get_prompt(
                    "golden_qa_generation",
                    question_type=q_type,
                    chunk_text=doc_text
                )

                # Request LLM completion
                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.config.get("llm", {}).get("max_tokens_to_sample", 1024)
                )
                response_text = response.choices[0].message.content

                # Parse YAML fields
                parsed_type, question, expected, difficulty = self._parse_llm_response(response_text)

                if not question or not expected:
                    logger.warning(f"Could not extract query or expected answer for chunk {chunk_id}. Skipping.")
                    continue

                # Add to dataset records
                qa_pairs.append({
                    "id": f"gen_qa_{idx+1}",
                    "type": parsed_type,
                    "question": question,
                    "expected_answer": expected,
                    "required_chunk": chunk_id,
                    "difficulty": difficulty,
                    "human_verified": False
                })

            except Exception as e:
                logger.error(f"Error generating QA pair for chunk {chunk_id}: {str(e)}")
                continue

        # 3. Save as JSONL (formatted output, one JSON record per line)
        try:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                for qa in qa_pairs:
                    f.write(json.dumps(qa) + "\n")
        except Exception as e:
            raise DatasetGeneratorError(f"Failed to write dataset records to file '{output_file}': {str(e)}") from e

        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Dataset generation complete. Generated {len(qa_pairs)} pairs in {latency_ms:.2f}ms.")
        
        # Explicit print statement as requested by requirement
        print("HUMAN REVIEW REQUIRED before using this dataset in CI")
        return output_file
