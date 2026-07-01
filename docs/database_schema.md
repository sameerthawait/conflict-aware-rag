# CA-RAG Database Schema Specifications

This document defines the storage layers and schema definitions used to support publication-grade Conflict-Aware RAG (CA-RAG) executions.

---

## 1. Relational Layer (PostgreSQL)

```sql
-- Claims table storing atomic facts extracted from document chunks
CREATE TABLE claims (
  claim_id UUID PRIMARY KEY,
  chunk_id VARCHAR(255) NOT NULL,
  doc_id VARCHAR(255) NOT NULL,
  source_title TEXT NOT NULL,
  claim_text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  claim_type VARCHAR(50) NOT NULL,
  confidence FLOAT NOT NULL,
  span_start INT NOT NULL,
  span_end INT NOT NULL,
  extracted_at TIMESTAMPTZ DEFAULT NOW()
);

-- NLI results mapping relationships between claims
CREATE TABLE nli_results (
  result_id UUID PRIMARY KEY,
  claim_a_id UUID REFERENCES claims(claim_id) ON DELETE CASCADE,
  claim_b_id UUID REFERENCES claims(claim_id) ON DELETE CASCADE,
  query_hash VARCHAR(64) NOT NULL,
  forward_label VARCHAR(20) NOT NULL,
  forward_entailment_score FLOAT NOT NULL,
  forward_contradiction_score FLOAT NOT NULL,
  forward_neutral_score FLOAT NOT NULL,
  backward_label VARCHAR(20) NOT NULL,
  backward_entailment_score FLOAT NOT NULL,
  backward_neutral_score FLOAT NOT NULL,
  backward_contradiction_score FLOAT NOT NULL,
  final_verdict VARCHAR(20) NOT NULL,
  contradiction_strength FLOAT NOT NULL,
  is_bidirectional BOOLEAN NOT NULL,
  model_used VARCHAR(100) NOT NULL,
  inference_time_ms INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Evidence clusters grouping similar claims
CREATE TABLE evidence_clusters (
  cluster_id UUID PRIMARY KEY,
  query_hash VARCHAR(64) NOT NULL,
  label TEXT NOT NULL,
  stance VARCHAR(20) NOT NULL,
  representative_claim_id UUID REFERENCES claims(claim_id),
  source_count INT NOT NULL,
  confidence FLOAT NOT NULL,
  internal_consistency FLOAT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Completed pipeline responses logs
CREATE TABLE ca_rag_responses (
  response_id UUID PRIMARY KEY,
  query TEXT NOT NULL,
  query_hash VARCHAR(64) NOT NULL,
  mode VARCHAR(20) NOT NULL,
  supporting_evidence TEXT,
  contradicting_evidence TEXT,
  areas_of_agreement JSONB,
  areas_of_disagreement JSONB,
  final_balanced_summary TEXT,
  overall_confidence FLOAT NOT NULL,
  conflict_clarity FLOAT NOT NULL,
  total_latency_ms INT NOT NULL,
  latency_breakdown JSONB,
  fallback_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User feedback metrics logs
CREATE TABLE conflict_feedback (
  feedback_id UUID PRIMARY KEY,
  response_id UUID REFERENCES ca_rag_responses(response_id) ON DELETE CASCADE,
  feedback_type VARCHAR(50) NOT NULL,
  claim_ids JSONB NOT NULL,
  user_note TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index mappings
CREATE INDEX idx_nli_query ON nli_results(query_hash);
CREATE INDEX idx_nli_verdict ON nli_results(final_verdict);
CREATE INDEX idx_claims_chunk ON claims(chunk_id);
CREATE INDEX idx_clusters_query ON evidence_clusters(query_hash);
CREATE INDEX idx_responses_query ON ca_rag_responses(query_hash);
CREATE INDEX idx_nli_strength ON nli_results(contradiction_strength);
```

---

## 2. Graph Layer (Neo4j)

Conflict Graphs are charted inside Neo4j using the following property graph schemas:

### Node Properties
- **`Claim`**:
  - `claim_id: STRING` (UUID)
  - `normalized_text: STRING`
  - `claim_type: STRING`
  - `confidence: FLOAT`
  - `created_at: TIMESTAMP`
- **`Document`**:
  - `doc_id: STRING`
  - `title: STRING`
  - `ingested_at: TIMESTAMP`
- **`Cluster`**:
  - `cluster_id: STRING` (UUID)
  - `label: STRING`
  - `stance: STRING`
  - `query_hash: STRING`
  - `created_at: TIMESTAMP`

### Relationship Types
- `(claim:Claim)-[:BELONGS_TO]->(cluster:Cluster)`
- `(claim:Claim)-[:EXTRACTED_FROM]->(doc:Document)`
- `(c1:Claim)-[:CONTRADICTS {strength: FLOAT, query_hash: STRING}]->(c2:Claim)`
- `(c1:Claim)-[:SUPPORTS {score: FLOAT, query_hash: STRING}]->(c2:Claim)`
- `(c1:Claim)-[:RELATED {similarity: FLOAT}]->(c2:Claim)`

---

## 3. Cache Layer (Redis)

Standard Redis keys mapping query and pipeline outputs:
- **Pipeline Responses**: `ca_rag:response:{response_id}` -> `CARAGResponse JSON` (TTL: 24 hours)
- **Visualization Graphs**: `ca_rag:graph:{response_id}` -> `D3.js Graph JSON` (TTL: 24 hours)
- **Claims Extraction Cache**: `ca_rag:claims:{query_hash}` -> `extracted claims array` (TTL: 1 hour)
- **NLI Pairwise Results**: `ca_rag:nli:{claim_a_id}:{claim_b_id}` -> `NLIResult JSON` (TTL: 6 hours)
