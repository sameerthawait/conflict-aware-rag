# System Architecture and Design Decisions

This document details the architectural specifications, component boundaries, latency budgets, and decision logs of the Conflict-Aware RAG (CA-RAG) system.

---

## 1. Data Flow Diagram

```text
USER QUERY
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    CA-RAG PIPELINE                      │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │ BM25         │    │ Vector       │                  │
│  │ Retriever    │    │ Retriever    │                  │
│  └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                          │
│         └─────────┬─────────┘                          │
│                   ▼                                    │
│         ┌─────────────────┐                            │
│         │ RRF Fusion +    │                            │
│         │ Cross-Encoder   │                            │
│         │ Re-ranker       │                            │
│         └────────┬────────┘                            │
│                  │ top-k chunks                        │
│                  ▼                                     │
│         ┌─────────────────┐                            │
│         │ CLAIM EXTRACTOR │ ← LLM + NLP                │
│         │ (atomic claims) │                            │
│         └────────┬────────┘                            │
│                  │ List[Claim]                         │
│                  ▼                                     │
│         ┌─────────────────┐                            │
│         │ NLI DETECTOR    │ ← DeBERTa NLI model        │
│         │ (E/C/N matrix)  │                            │
│         └────────┬────────┘                            │
│                  │ NLIMatrix                           │
│         ┌────────┴────────┐                            │
│         │ Contradictions? │                            │
│         └────────┬────────┘                            │
│         NO │     │ YES                                 │
│            ▼     ▼                                     │
│         Standard ┌────────────────┐                    │
│         RAG      │ EVIDENCE       │                    │
│         Pipeline │ CLUSTERER      │                    │
│                  │ (Spectral)     │                    │
│                  └───────┬────────┘                    │
│                          │ List[EvidenceCluster]       │
│                          ▼                             │
│                  ┌────────────────┐                    │
│                  │ CONFLICT GRAPH │→ Neo4j             │
│                  │ BUILDER        │  persist           │
│                  └───────┬────────┘                    │
│                          │ ConflictGraph               │
│                          ▼                             │
│                  ┌────────────────┐                    │
│                  │ CONFIDENCE     │                    │
│                  │ SCORER (5-dim) │                    │
│                  └───────┬────────┘                    │
│                          │ ResponseConfidence          │
│                          ▼                             │
│                  ┌────────────────┐                    │
│                  │ CITATION       │← GATE 1            │
│                  │ PREFLIGHT      │                    │
│                  └───────┬────────┘                    │
│                          │                             │
│                          ▼                             │
│                  ┌────────────────┐                    │
│                  │ CA-RAG         │                    │
│                  │ GENERATOR      │← LLM (Claude/Llama)│
│                  │ (structured)   │                    │
│                  └───────┬────────┘                    │
│                          │                             │
│                          ▼                             │
│                  ┌────────────────┐                    │
│                  │ HALLUCINATION  │← GATE 2            │
│                  │ VERIFIER       │                    │
│                  └───────┬────────┘                    │
│                          │                             │
│                          ▼                             │
│                   CA-RAG Response                      │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Component Specifications

### 2.1 Ingestion Component
- **Document Loader** (`src/ingestion/document_loader.py`): Parses raw documents (PDF, DOCX, TXT, MD) and extracts text and page metadata.
- **Semantic Chunker** (`src/ingestion/chunker.py`): Performs token-aware grouping of sentences, applying a target overlap (100 tokens), and prepends document summaries as "context bridges".

### 2.2 Retrieval Component
- **BM25 Okapi Index** (`src/retrieval/bm25_retriever.py`): Measures exact keyword term matching. Stores pickle indexes on disk, rebuilds automatically when ChromaDB element counts mismatch.
- **Vector Search Client** (`src/ingestion/vector_store.py`): Embeds queries using local `all-mpnet-base-v2` to query ChromaDB collection.
- **RRF Merger** (`src/retrieval/fusion.py`): Combines vector and BM25 results, normalizing outputs into reciprocal ranks.
- **Reranker** (`src/retrieval/reranker.py`): Rescores candidates using local MiniLM Cross-Encoder, with LLM API relevance check fallback.

### 2.3 CA-RAG Component
- **Claim Extractor** (`src/ca_rag/claim_extractor.py`): Segregates raw chunks into atomic factual assertions, normalizes term abbreviations, and encodes texts.
- **NLI Contradiction Detector** (`src/ca_rag/nli_detector.py`): Executes local DeBERTa-v3 sequence classification to map entailment and contradiction scores.
- **Evidence Clusterer** (`src/ca_rag/evidence_clusterer.py`): Groups claims using affinity-based Spectral Clustering with the eigengap heuristic.
- **Conflict Graph Builder** (`src/ca_rag/conflict_graph.py`): Maps claims into directed NetworkX graphs and upserts to persistent Neo4j instances.
- **Confidence Scorer** (`src/ca_rag/confidence_scorer.py`): Implements a 5-dimensional scoring model (Relevance, Source Quality, Citation Volume, Disagreement, Freshness).
- **CA-RAG Generator** (`src/ca_rag/ca_rag_generator.py`): Synthesizes structured multi-perspective responses and reasons conflicts on-demand.
- **CA-RAG Master Pipeline** (`src/ca_rag/pipeline.py`): Orchestrates CA-RAG stages, maintaining latency budgets and standard pipeline fallbacks.

---

## 3. Design Decisions & Trade-offs

### 3.1 NLI-based Contradiction Detection vs. Direct LLM Auditing
- **Speed and Determinism**: Querying a 70B LLM for all $O(N^2)$ claim pairs creates massive latency bottlenecks and high token charges. Loading a local `nli-deberta-v3-base` cross-encoder enables execution in milliseconds on CPU/GPU, offering reproducible probability scores for entailment and contradiction. LLMs are only retained as a final safety fallback.

### 3.2 Spectral Clustering vs. Flat Hierarchies
- **Dynamic Viewpoint Grouping**: Traditional RAG partitions stances simply by source boundaries. CA-RAG constructs an affinity matrix from bidirectional NLI outputs (Entailment pulls, Contradiction pushes). Applying Spectral Clustering with the eigengap heuristic allows dynamically discovering the number of independent viewpoints (e.g. 2, 3, or more perspectives) without hardcoded assumptions.

### 3.3 5-Dimensional Confidence Scoring
- **Contextual Trust**: Standard confidence indicators are limited to simple retrieval distances. CA-RAG computes confidence along multiple orthogonal dimensions: Retrieval Relevance, Source Publishing Authority, citation counts, contradiction involvement, and domain-adjusted chronological age decay.

---

## 4. Latency Budget Breakdown

CA-RAG is allocated a budget of **< 10.0 seconds** for full multi-perspective synthesis, with standard RAG fallbacks restricted to **< 3.0 seconds**:

| Stage | Target Latency | Maximum Budget | Description |
| :--- | :--- | :--- | :--- |
| **Hybrid Retrieval** | 500 ms | 800 ms | Vector + BM25 parallel searches + Reranker. |
| **Claim Extraction** | 1200 ms | 2000 ms | Atomic assertion LLM parsing (parallel execution). |
| **NLI Classification** | 600 ms | 1500 ms | Local DeBERTa bidirectional pairwise checks. |
| **Spectral Clustering** | 200 ms | 500 ms | Laplacian eigenvalues + K-means grouping. |
| **Graph Building** | 100 ms | 300 ms | NetworkX representation + async Neo4j persist. |
| **Confidence Scoring** | 100 ms | 200 ms | 5-dimensional weights calculations. |
| **Citation Preflight** | 400 ms | 800 ms | Sufficiency check quality gate. |
| **Response Generation** | 2000 ms | 3000 ms | Multi-perspective synthesis completion. |
| **Hallucination Audit** | 800 ms | 1500 ms | Anti-hallucination verification gate. |
| **Total CA-RAG Pipeline**| **5900 ms** | **10000 ms** | Full Multi-Perspective pipeline execution. |
