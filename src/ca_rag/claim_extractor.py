import time
import uuid
import logging
import json
import asyncio
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from openai import OpenAI

from src.utils.prompt_manager import PromptManager
from src.ingestion.vector_store import SearchResult

logger = logging.getLogger("rag_system.ca_rag.claim_extractor")

class ClaimType(str, Enum):
    FACTUAL = "FACTUAL"
    QUANTITATIVE = "QUANTITATIVE"
    CAUSAL = "CAUSAL"
    TEMPORAL = "TEMPORAL"
    COMPARATIVE = "COMPARATIVE"
    RECOMMENDATION = "RECOMMENDATION"

@dataclass
class Claim:
    claim_id: str
    chunk_id: str
    doc_id: str
    source_title: str
    claim_text: str
    normalized_text: str
    claim_type: ClaimType
    confidence: float
    span_start: int
    span_end: int
    extracted_at: datetime
    embedding: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "source_title": self.source_title,
            "claim_text": self.claim_text,
            "normalized_text": self.normalized_text,
            "claim_type": self.claim_type.value,
            "confidence": self.confidence,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "extracted_at": self.extracted_at.isoformat(),
            "embedding": self.embedding
        }


class ClaimExtractor:
    """Extracts, cleans, and normalizes atomic claims from document chunks using LLM and NLP heuristics."""

    GLOSSARY = {
        "nsclc": "non-small cell lung cancer",
        "egfr": "epidermal growth factor receptor",
        "tki": "tyrosine kinase inhibitor",
        "dfs": "disease-free survival",
        "os": "overall survival",
        "pfs": "progression-free survival",
        "rag": "retrieval-augmented generation",
        "llm": "large language model",
        "nli": "natural language inference",
        "api": "application programming interface",
        "ci/cd": "continuous integration and continuous delivery",
        "ai": "artificial intelligence",
        "ml": "machine learning"
    }

    HEDGING_PHRASES = [
        "it is believed that", "some argue that", "some argue", "reportedly", 
        "it appears that", "according to reports", "arguably", "presumably", 
        "allegedly", "it is thought that", "it is claimed that", "sources claim that"
    ]

    def __init__(
        self,
        config: Dict[str, Any],
        prompt_manager: PromptManager,
        vector_store: Any,
        client: OpenAI
    ) -> None:
        self.config = config
        self.prompt_manager = prompt_manager
        self.vector_store = vector_store
        self.client = client

    def normalize(self, claim_text: str) -> str:
        """Normalizes raw claim text by removing hedging, resolving pronouns, and expanding glossary items."""
        text = claim_text.strip().lower()

        # Remove hedging phrases
        for phrase in self.HEDGING_PHRASES:
            if text.startswith(phrase):
                text = text[len(phrase):].strip()
            text = text.replace(f" {phrase} ", " ")

        # Clean up double spaces resulting from replacement
        while "  " in text:
            text = text.replace("  ", " ")

        # Expand abbreviations based on glossary
        words = text.split()
        for i, word in enumerate(words):
            # Clean punctuation from word for glossary matching
            clean_word = "".join(c for c in word if c.isalnum())
            if clean_word in self.GLOSSARY:
                expanded = self.GLOSSARY[clean_word]
                # Retain punctuation if present in original word
                word_expanded = word.replace(clean_word, expanded)
                words[i] = word_expanded
        text = " ".join(words)

        # Capitalize first letter to make it a clean sentence
        if text:
            text = text[0].upper() + text[1:]
        return text

    def extract(self, chunk_text: str, chunk_id: str, source_metadata: Dict[str, Any]) -> List[Claim]:
        """Extracts atomic claims from a single chunk of text."""
        source_title = source_metadata.get("title", "Unknown Source")
        doc_id = source_metadata.get("doc_id", "Unknown Doc")

        try:
            prompt_text = self.prompt_manager.get_prompt(
                "claim_extractor_prompt",
                chunk_id=chunk_id,
                source_title=source_title,
                chunk_text=chunk_text
            )

            llm_model = self.config.get("llm", {}).get("model_name", "meta/llama-3.3-70b-instruct")
            temperature = self.config.get("llm", {}).get("temperature", 0.0)

            response = self.client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=temperature,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content.strip()
            # Handle possible markdown json formatting blocks
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```json"):
                    content = "\n".join(lines[1:-1])
                elif lines[0].startswith("```"):
                    content = "\n".join(lines[1:-1])

            data = json.loads(content)
            # Expecting a JSON object containing a claims array, or just a JSON array
            raw_claims = []
            if isinstance(data, list):
                raw_claims = data
            elif isinstance(data, dict):
                # Search for arrays in the dictionary values
                for v in data.values():
                    if isinstance(v, list):
                        raw_claims = v
                        break
                else:
                    raw_claims = [data]

            claims = []
            embedding_model = getattr(self.vector_store, "embedding_model", None)

            for item in raw_claims:
                claim_text = item.get("claim_text", "").strip()
                if not claim_text:
                    continue

                normalized_text = item.get("normalized_text", "")
                if not normalized_text:
                    normalized_text = self.normalize(claim_text)
                else:
                    normalized_text = self.normalize(normalized_text)

                ctype_str = item.get("claim_type", "FACTUAL").upper()
                try:
                    ctype = ClaimType(ctype_str)
                except ValueError:
                    ctype = ClaimType.FACTUAL

                confidence = float(item.get("confidence", 0.8))
                span_start = int(item.get("span_start", 0))
                span_end = int(item.get("span_end", len(chunk_text)))

                # Embed normalized text
                emb = []
                if embedding_model is not None:
                    try:
                        emb = embedding_model.encode(normalized_text).tolist()
                    except Exception as e:
                        logger.warning(f"Failed to encode claim text: {str(e)}")

                claims.append(Claim(
                    claim_id=str(uuid.uuid4()),
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    source_title=source_title,
                    claim_text=claim_text,
                    normalized_text=normalized_text,
                    claim_type=ctype,
                    confidence=confidence,
                    span_start=span_start,
                    span_end=span_end,
                    extracted_at=datetime.utcnow(),
                    embedding=emb
                ))

            return claims

        except Exception as e:
            logger.error(f"Failed to extract claims from chunk {chunk_id}: {str(e)}")
            return []

    async def batch_extract(self, chunks: List[SearchResult]) -> Dict[str, List[Claim]]:
        """Extracts claims from multiple chunks in parallel, deduplicating duplicates."""
        loop = asyncio.get_event_loop()
        tasks = []
        for chunk in chunks:
            # Wrap the synchronous extraction call in a thread pool task
            task = loop.run_in_executor(
                None,
                self.extract,
                chunk.text,
                chunk.chunk_id,
                chunk.metadata
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        chunk_claims_map = {}
        all_normalized_claims = set()

        for chunk, claim_list in zip(chunks, results):
            deduplicated_list = []
            for claim in claim_list:
                key = (claim.normalized_text.lower(), claim.doc_id)
                if key not in all_normalized_claims:
                    all_normalized_claims.add(key)
                    deduplicated_list.append(claim)
            chunk_claims_map[chunk.chunk_id] = deduplicated_list

        return chunk_claims_map
