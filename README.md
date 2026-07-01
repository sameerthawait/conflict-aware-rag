# Conflict-Aware Retrieval-Augmented Generation (CA-RAG) Research System

A high-trust, multi-perspective RAG exploration system built for researchers, clinicians, and legal professionals to identify, cluster, and analyze logical contradictions and differing stances in scientific literature.

---

## 1. System Architecture Overview

```text
       +---------------------------------------------+
       |               Document Ingestion            |
       |  (PDF/Docx/MD Loader -> Semantic Chunker)   |
       +----------------------+- --------------------+
                              |
                              v
             +----------------+----------------+
             |         Chroma Vector DB        |
             |  (mpnet semantic & keyword ids) |
             +----------------+----------------+
                              ^
                              | 1. Query Expansion
                              |
     +------------------------+--------------------------+
     |                       API Query                   |
     |                       (FastAPI)                   |
     +---------+------------------------------+----------+
               |                              |
               | 2. Parallel Search           | 2. Parallel Search
               v                              v
       +-------+-------+              +-------+-------+
       | Vector Search |              |  BM25 Search  |
       |  (Semantic)   |              |   (Keyword)   |
       +-------+-------+              +-------+-------+
               |                              |
               +--------------+---------------+
                              |
                              v 3. Reciprocal Rank Fusion (RRF)
                     +--------+--------+
                     |  RRF Candidate  |
                     |     Merger      |
                     +--------+--------+
                              |
                              v 4. Cross-Encoder Reranking
                     +--------+--------+
                     |  Reranked Top-K |
                     |     Context     |
                     +--------+--------+
                              |
                              v 5. Quality Gate 1: Citation Preflight Gate
            [Sufficient / Partial?]       [Insufficient?]
                      |                          |
                      | (Yes)                    | (No - Bypasses LLM)
                      v                          v
             +--------+--------+       +---------+----------+
             |  LLM Generator  |       | Immediate Refusal  |
             | (Context Answer)|       |      Message       |
             +--------+--------+       +--------------------+
                      |
                      v 6. Quality Gate 2: Anti-Hallucination Audit
             +--------+--------+
             |   Verified RAG  |
             |     Response    |
             +-----------------+
```

---

## 2. Key Features

### 💻 Frontend Chat Workspace
* **Academic Design System:** Tailored white-contrast, typography-rich dashboard designed for academic journals and clinical settings.
* **Side-by-Side Perspective Columns:** Groups contradictory findings and differing viewpoints side-by-side with star-rated evidence scores and collapsible source lists.
* **5-Dimensional Credibility Radar:** Uses Recharts radar maps to score information quality across five metrics: Retrieval Relevance, Source Quality, Citation Volume, Contradiction Resistance, and Consensus.
* **Visual Conflict Indicators:** Disagreement Meters and sliding banners indicate the semantic and logical strength of contradictions (0-10) using micro-animations.
* **Citation Explorer:** Optimized inline citation pills featuring GPU-accelerated, CSS-only tooltip hover cards for direct chunk lookups.

### 🧠 Backend NLP & NLI Engine
* **Atomic Claim Extraction:** Parses raw text chunks into individual factual assertions, expanding abbreviations and resolving pronouns.
* **Bidirectional NLI Classification:** Analyzes claim pairings using Natural Language Inference models to detect logical contradictions:
  $$\max(p_{\text{fwd, con}}, p_{\text{bwd, con}}) \ge 0.55$$
* **Spectral Stance Clustering:** Constructing claim affinity matrices (attraction for entailment, repulsion for contradiction) and applying Laplacian Eigengap heuristics to discover the optimal number of stances.

### ⚙️ Production Hardening
* **Redis Caching & Semantic cache:** Cache query response embeddings to bypass redundant LLM generation bills for semantically similar searches.
* **API Protection & Rate Limiting:** Enforces payload size ceilings, query character caps, and Redis-backed dynamic rate limits (Requests Per Minute and Tokens Per Day limits) mapped to tiered API keys.
* **Structured telemetry:** Structured logging pipelines and Prometheus metrics exporters linked to Grafana dashboard analytics.

---

## 3. Technology Stack

* **Frontend:** Next.js 14 (App Router), React, Zustand State Management, TanStack Query, Tailwind CSS, Recharts (visualizations), Lucide React.
* **Backend:** FastAPI, Python 3.11, ChromaDB (Vector persistence), Redis (caching and rate limits), PyTorch & HuggingFace (embedding and cross-encoder models).
* **CI/CD:** GitHub Actions workflow verifying Python linting (`ruff`), strict type safety (`mypy`), PyTest suits, Trivy security container scans, and Next.js frontend ESLint/Typecheck builds.

---

## 4. Setup & Operations

### A. Run Docker Stack
Run the following from the root directory to spin up the API server, database, Redis cache, Prometheus, and Grafana:
```bash
# 1. Copy environment template
cp .env.example .env
# Open .env and insert your NVIDIA_API_KEY from build.nvidia.com

# 2. Build and start containers
docker compose up -d --build
```

### B. Ingest Research Papers
Place your Markdown, text, or PDF documents under `data/raw/` and trigger the indexing pipeline:
```bash
docker compose exec rag-api python scripts/ingest.py --path data/raw
```

### C. Run the Frontend Workspace
Ensure Node.js is installed locally, navigate to the `frontend/` directory, and launch the dev server:
```bash
cd frontend
npm install
npm run dev -- -p 3002
```
Access the workspace at `http://localhost:3002`.

### D. Authorize API Credentials
1. Open `http://localhost:3002/admin`.
2. Input one of the pre-configured keys defined in `config/config.yaml`:
   * **Premium Tier Key:** `admin-secret-key-123`
   * **Standard Tier Key:** `standard-secret-key-456`
3. Click **Save Key Reference** to authenticate.

---

## 5. Administrative Controls

Manage API keys and caches via the CLI:
```bash
# Generate a new Premium API key
docker compose exec rag-api python scripts/admin.py create-api-key --name staging-app --tier premium

# List all active key references
docker compose exec rag-api python scripts/admin.py list-keys

# Invalidate all semantic query caches
docker compose exec rag-api python scripts/admin.py invalidate-cache
```

---

## 6. Testing & CI/CD Pipelines
* **Deployment Verifications (`scripts/deploy.sh`):** Executes pre-checks, runs PyTest tests, and packages target docker builds.
* **Evaluation Reports (`scripts/run_evaluation.py`):** Runs the RAG evaluation suite against the golden dataset.
* **Scheduled Backups (`scripts/backup.sh`):** Compresses and archives database collections, indices, and templates, keeping the last 7 days locally.