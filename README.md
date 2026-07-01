# Production-Ready Hybrid RAG System

This repository contains a production-ready, highly-optimized Retrieval-Augmented Generation (RAG) system built with FastAPI, LangChain orchestration, ChromaDB vector storage, Reciprocal Rank Fusion (RRF), Cross-Encoder reranking, and dual quality gate safety gates.

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

## 2. Production Security & Hardening (Phase 4)

This system implements enterprise-level hardening for production operations:

1. **API Authentication & Rate Limiting**:
   - SHA-256 hashed API keys validated at runtime (no plaintext storage).
   - Multi-tier support (Premium / Standard) with dynamic rate limits (RPM and TPD limits).
   - Redis-backed rate limits with automatic memory fallback in case of Redis outages.

2. **API Protection**:
   - **Payload Caps**: Enforces strict request body limits (e.g. 10KB size limit) to prevent DoS.
   - **Input Sanitization**: HTML tag stripping and prompt injection mitigation checks.
   - **Request ID Tracking**: Generates unique tracking IDs for every request, threading them through log traces.

3. **High-Performance Caching & Connection Pools**:
   - **Connection Pooling**: Thread-safe ChromaDB connection pool sharing a pre-warmed embedding model to avoid CPU/memory leaks.
   - **Semantic Cache**: Redis-backed cache evaluating cosine similarities of query embeddings. Avoids redundant LLM billing for identical or semantically close queries.

4. **Token Cost Budgeting**:
   - Tracks token counts and estimates request costs in USD.
   - Hard blocks further LLM usage if daily/monthly budgets are exhausted, with warning audits at 80%.

5. **Observability Stacks**:
   - **Structured Logs**: Access, error, and audit logging outputs formatted in JSON.
   - **Metrics Engine**: Prometheus instrumentation exporting queries counters, latencies, circuit breakers, cache hits, queue depths, and token metrics.
   - **Grafana Dashboard**: Preconfigured dashboards visualizer provisioned automatically.

---

## 3. Quickstart (Under 10 Minutes)

Follow these steps to run the complete stack locally using Docker Compose:

```bash
# 1. Clone repository and setup environment
cp .env.example .env
# Edit .env and enter your NVIDIA_API_KEY from build.nvidia.com

# 2. Start the full docker container stack
docker compose up -d --build

# 3. Check application health
curl http://localhost:8000/health/ready

# 4. Ingest sample documents into the system
# Place document files in data/raw/ and run:
docker compose exec rag-api python scripts/ingest.py --path data/raw

# 5. Query the RAG API via curl (requires standard key header)
# Default keys configured in config.yaml:
# - Standard Key: standard-secret-key-456
# - Admin Key: admin-secret-key-123
curl -X POST "http://localhost:8000/query" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: standard-secret-key-456" \
     -d '{"query": "What is the system architecture?"}'
```

---

## 4. Administrative Command Line Interface

Use the CLI script to manage keys, check budgets, and invalidate cache:

```bash
# Generate a new premium API key
python scripts/admin.py create-api-key --name staging-app --tier premium

# List all configured API keys
python scripts/admin.py list-keys

# Invalidate all semantic query cache items in Redis
python scripts/admin.py invalidate-cache

# View live Redis budgets usage and rate-limiter states
python scripts/admin.py show-metrics
```

---

## 5. Operations & CI/CD Deployment

- **Preflight Deployment Verification (`scripts/deploy.sh`)**: Runs evaluation pipelines, asserts unit/integration test success, and builds the target docker image. Blocks builds if metrics slip below thresholds.
- **Scheduled Backups (`scripts/backup.sh`)**: Automatically bundles Chroma database folders, BM25 indices, prompt templates, and configs into a compressed archive. Retains the last 7 days locally.
- **Operational Manual (`docs/runbook.md`)**: Contains detailed instructions for handling open circuit breakers, high error rates, budget warnings, and database recovery.






ignore this(personal use only)
Step 3 — The Master Prompt To Give Antigravity First
Every single session, paste this at the start before anything else:
You are the principal engineer on the CA-RAG project.

FIRST: Read these files completely before doing anything:
- project-brain/system/system.md
- project-brain/memory/architecture.md
- project-brain/memory/backend.md
- project-brain/cache/recent-context.md
- project-brain/tasks/active.md

RULES:
1. Never analyze files not listed in your task
2. Always use load_config() not get_config()
3. Always show before/after for every change
4. Always run the verify command from system.md after fixing
5. Always update project-brain/cache/recent-context.md 
   at the end of every session
6. Always append completed work to project-brain/tasks/completed.md
7. Never create new files without checking memory/ first

CURRENT TASK: [PASTE YOUR TASK HERE]

Read the brain files first. Then work.

How This Saves You Tokens
Without Project BrainWith Project BrainAgent reads entire codebase every sessionAgent reads only relevant memory filesRepeats same analysis every timeLoads cache from last sessionRediscovers bugs already fixedChecks known bugs list firstRe-asks what functions are calledReads backend.md~50,000 tokens per session~5,000 tokens per session
That is roughly 10x token savings per session.

Step 4 — After Every Session
Tell Antigravity at the end:
Update project-brain/cache/recent-context.md with:
- What we worked on today
- What files were changed
- What is the next task
- Any new bugs discovered
- Current state of the system
This means next session starts exactly where you left off with zero re-analysis.
Set this up now before giving any more fix prompts. It will save significant time for the rest of your project.





Use Serena to activate the current workspace and understand the project structure.

Read the repository, identify the architecture, technologies, entry points, important modules, coding conventions, and dependencies.

If this project has not been onboarded, run Serena onboarding.

From now on, always use Serena for code navigation and refactoring, Context7 for up-to-date library documentation, GitHub MCP for repository operations, Playwright for browser testing, Filesystem MCP for file operations, and Sequential Thinking MCP for complex reasoning before making changes.

Do not modify any code until you fully understand the project. Present a brief architecture summary first, then wait for my instructions.