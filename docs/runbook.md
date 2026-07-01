# Production Operational Runbook: RAG System

This document outlines standard operating procedures, monitoring guides, disaster recovery steps, and escalation pathways for the production RAG (Retrieval-Augmented Generation) System.

---

## 1. System Architecture Overview

The system consists of the following containerized services:
- **FastAPI Backend (`rag-api`)**: Orchestrates document ingestion, query queueing, hybrid retrieval, and NVIDIA NIM LLM generations. Exposes `/health/ready` and `/metrics`.
- **ChromaDB Vector Store (`chromadb`)**: Stores document embeddings. Accessible internally only.
- **Redis Cache Store (`redis`)**: Backs rate limits, budget enforcement, and semantic cache.
- **Prometheus (`prometheus`)**: Scrapes `/metrics` from the API backend.
- **Grafana (`grafana`)**: Visual analytics dashboard.

---

## 2. Alerts & Troubleshooting Directory

### Alert: `HighErrorRate`
- **Condition**: API error rate > 5% within 1 minute.
- **Diagnostics**:
  1. Inspect API logs for HTTP 500 status codes:
     ```bash
     docker logs rag-api | grep '"status":500'
     ```
  2. Verify if the upstream NVIDIA NIM LLM client is failing (e.g., HTTP 401, 403, or 429).
  3. Verify connection to ChromaDB and Redis:
     ```bash
     curl http://localhost:8000/health/ready
     ```

### Alert: `HighLatency`
- **Condition**: P95 query processing latency > 5s.
- **Diagnostics**:
  1. Inspect Grafana panel **Latency Percentiles by Stage** to isolate the bottleneck (e.g., `retrieval`, `generation`, or `queue`).
  2. If bottleneck is `generation`, check downstream NVIDIA API status page.
  3. If bottleneck is `retrieval`, verify ChromaDB CPU load:
     ```bash
     docker stats chromadb
     ```
     Optimize ChromaDB index sizes or rebuild the index using the backup script if fragmentation has occurred.

### Alert: `CircuitBreakerOpen`
- **Condition**: `rag_circuit_breaker_state` gauge equals `1`.
- **Diagnostics**:
  - The circuit breaker tripped to protect downstream services from cascading failure due to recurring errors.
  - **Resolution**:
    1. Monitor logs. The circuit breaker will automatically enter `HALF-OPEN` after 30 seconds (configurable) and try sending a test query.
    2. If it continues to open, verify network connectivity to `https://integrate.api.nvidia.com/v1`.
    3. Verify that the `NVIDIA_API_KEY` environment variable has not expired or been revoked.

### Alert: `BudgetWarning`
- **Condition**: Token consumption exceeds 80% of the daily allowance (400,000 / 500,000 tokens).
- **Diagnostics**:
  1. Run the administrative tool to see who is consuming tokens:
     ```bash
     python scripts/admin.py show-metrics
     ```
  2. Run the admin CLI to fetch cost reports from the active server:
     ```bash
     curl -H "X-API-Key: <ADMIN_KEY>" http://localhost:8000/admin/costs
     ```
  3. Coordinate with product managers to upgrade standard user limits or allocate a higher token budget in `config/config.yaml` if needed.

### Alert: `QueueFull`
- **Condition**: Request queue depth > 40 items.
- **Diagnostics**:
  - Indicates that incoming query rates exceed the processing capacity of the generating worker threads.
  - **Resolution**:
    1. Scale standard FastAPI worker processes or scale container replicas in `docker-compose.yml`.
    2. Check if LLM response generation latency has spiked, causing worker starvation.

---

## 3. Database Operations & Backups

### Scheduled Backups
Data backups run automatically via cron job using `scripts/backup.sh`.
- **Manual Backup Trigger**:
  ```bash
  ./scripts/backup.sh
  ```
- **Bucket Configuration**: Define `BACKUP_BUCKET_URI=s3://my-rag-backups` in `.env`.

### Database Restore Procedure
In case of database corruption or hardware replacement:
1. Stop the target services:
   ```bash
   docker compose stop rag-api chromadb
   ```
2. Locate the latest archive in the `./backups` directory (e.g., `rag_backup_20260626_120000.tar.gz`).
3. Restore files to project root:
   ```bash
   tar -xzf backups/rag_backup_20260626_120000.tar.gz -C .
   ```
4. Restart services and check health logs:
   ```bash
   docker compose start chromadb rag-api
   docker logs rag-api
   ```

---

## 4. Key Management & Rotation

API keys must be rotated every 90 days or immediately upon compromise.

### Dynamic Key Addition
1. Generate and register a new key (e.g., standard tier):
   ```bash
   python scripts/admin.py create-api-key --name client-app-prod --tier standard
   ```
2. Distribute the generated `rag-...` clear text API key to the client application.
3. Verify client connectivity using the new key:
   ```bash
   curl -H "X-API-Key: rag-yournewkeyhere" http://localhost:8000/health/ready
   ```

### Key Revocation
1. Revoke the old key by its name:
   ```bash
   python scripts/admin.py revoke-api-key --name client-app-old
   ```
2. Confirm the key list matches expectations:
   ```bash
   python scripts/admin.py list-keys
   ```

---

## 5. Escalation Matrix

If recovery procedures fail to resolve active alerts:
1. **Tier 1 (DevOps/SRE)**: Check container states, docker network routing, and host CPU/memory allocations.
2. **Tier 2 (AI/ML Engineer)**: Check NVIDIA NIM billing credentials, model availability, semantic cache hits, and vector storage indexing logic.
3. **Tier 3 (Lead Architect)**: Codebase patching, schema updates, fallback strategy adjustments.
