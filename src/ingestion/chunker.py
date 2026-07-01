import logging
import re
from typing import List, Dict, Any, Optional
from openai import OpenAI
from src.utils.prompt_manager import PromptManager
from src.utils.token_counter import count_tokens, truncate_to_token_limit
from src.ingestion.document_loader import Document

logger = logging.getLogger("rag_system.ingestion.chunker")


class ChunkerError(Exception):
    pass


class Chunk:
    def __init__(self, chunk_id, doc_id, text, token_count, metadata, summary):
        self.chunk_id = chunk_id
        self.doc_id = doc_id
        self.text = text
        self.token_count = token_count
        self.metadata = metadata
        self.summary = summary

    def __repr__(self):
        return f"Chunk(id={self.chunk_id}, doc_id={self.doc_id}, tokens={self.token_count})"


class SemanticChunker:
    def __init__(self, config: Dict[str, Any], prompt_manager: PromptManager) -> None:
        self.config = config
        self.prompt_manager = prompt_manager
        chunk_conf = config.get("chunking", {})
        self.min_tokens = chunk_conf.get("min_tokens", 50)
        self.max_tokens = chunk_conf.get("max_tokens", 500)
        self.target_tokens = chunk_conf.get("target_tokens", 300)
        self.overlap_tokens = chunk_conf.get("overlap_tokens", 100)
        llm_conf = config.get("llm", {})
        self.llm_model = llm_conf.get("model_name", "meta/llama-3.3-70b-instruct")
        self.temperature = llm_conf.get("temperature", 0.0)
        self.max_tokens_to_sample = llm_conf.get("max_tokens_to_sample", 1024)

    def _split_into_sentences(self, text: str) -> List[str]:
        if not text.strip():
            return []
        paragraphs = text.split("\n\n")
        sentences = []
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            para_sentences = re.split(r'(?<=[.!?])\s+', paragraph.strip())
            for sent in para_sentences:
                if sent.strip():
                    sentences.append(sent.strip())
        return sentences

    def _generate_summary_via_llm(self, text: str, client) -> str:
        # First line check: If client is None, skip summarization gracefully
        if client is None:
            return ""
        try:
            prompt = self.prompt_manager.get_prompt("chunk_summarizer", chunk_text=text)
            # Add timeout=10 to chat completions to prevent indefinite hanging
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens_to_sample,
                timeout=10
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"Summary skipped: {str(e)}")
            return ""

    def chunk_document(self, doc, doc_id, document_summary="", client=None):
        logger.info(f"Chunking document '{doc_id}' with title: '{doc.metadata.get('title')}'")
        sentences = self._split_into_sentences(doc.text)
        if not sentences:
            logger.warning(f"Document {doc_id} has no text content to chunk.")
            return []

        sentence_tokens = []
        for sent in sentences:
            try:
                t_count = count_tokens(sent)
                sentence_tokens.append((sent, t_count))
            except Exception as e:
                raise ChunkerError(f"Failed to count tokens: {str(e)}") from e

        chunks_raw_text = []
        current_sentences = []
        current_tokens = 0
        idx = 0

        while idx < len(sentence_tokens):
            sent, t_count = sentence_tokens[idx]
            if t_count > self.max_tokens:
                sent = truncate_to_token_limit(sent, self.max_tokens)
                t_count = count_tokens(sent)
            if current_tokens + t_count <= self.target_tokens:
                current_sentences.append(sent)
                current_tokens += t_count
                idx += 1
            else:
                if current_sentences:
                    chunks_raw_text.append(" ".join(current_sentences))
                    overlap_collected = 0
                    backtrack_steps = 0
                    for rev_idx in range(len(current_sentences) - 1, -1, -1):
                        st = count_tokens(current_sentences[rev_idx])
                        if overlap_collected + st <= self.overlap_tokens:
                            overlap_collected += st
                            backtrack_steps += 1
                        else:
                            break
                    # Prevent infinite loop by ensuring index always moves forward
                    backtrack_steps = min(backtrack_steps, len(current_sentences) - 1)
                    current_sentences = []
                    current_tokens = 0
                    idx = idx - backtrack_steps
                    if backtrack_steps == 0:
                        idx += 1
                else:
                    current_sentences.append(sent)
                    current_tokens += t_count
                    idx += 1

        if current_sentences:
            chunks_raw_text.append(" ".join(current_sentences))

        final_chunks = []
        document_title = doc.metadata.get("title", "Untitled Document")
        if not document_summary:
            document_summary = "This document contains technical content and reference information."

        for c_idx, raw_text in enumerate(chunks_raw_text):
            tok_count = count_tokens(raw_text)
            if tok_count < self.min_tokens and len(chunks_raw_text) > 1:
                if final_chunks:
                    prev_chunk = final_chunks[-1]
                    new_raw_text = prev_chunk.metadata["raw_text"] + " " + raw_text
                    summary = self._generate_summary_via_llm(new_raw_text, client)
                    bridged_text = self.prompt_manager.get_prompt(
                        "chunking_context_bridge",
                        document_title=document_title,
                        document_summary=document_summary,
                        chunk_text=new_raw_text
                    )
                    prev_chunk.text = bridged_text
                    prev_chunk.token_count = count_tokens(bridged_text)
                    prev_chunk.summary = summary
                    prev_chunk.metadata["raw_text"] = new_raw_text
                    prev_chunk.metadata["summary"] = summary
                    continue

            summary = self._generate_summary_via_llm(raw_text, client)
            try:
                bridged_text = self.prompt_manager.get_prompt(
                    "chunking_context_bridge",
                    document_title=document_title,
                    document_summary=document_summary,
                    chunk_text=raw_text
                )
            except Exception as e:
                raise ChunkerError(f"Failed to construct context bridge: {str(e)}") from e

            chunk_id = f"{doc_id}_chunk_{c_idx}"
            chunk_metadata = doc.metadata.copy()
            chunk_metadata.update({
                "chunk_index": c_idx,
                "raw_text": raw_text,
                "summary": summary
            })
            final_chunks.append(Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                text=bridged_text,
                token_count=count_tokens(bridged_text),
                metadata=chunk_metadata,
                summary=summary
            ))

        logger.info(f"Generated {len(final_chunks)} chunks for document {doc_id}")
        return final_chunks
