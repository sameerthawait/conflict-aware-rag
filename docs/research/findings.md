# Multi-Perspective RAG Evaluation & Benchmark Findings

**Date:** 2026-06-27 16:48:38

## Contradiction Detection Metrics

| Metric | Value |
| --- | --- |
| Total Cases | 50 |
| True Positives (TP) | 0 |
| False Positives (FP) | 0 |
| True Negatives (TN) | 22 |
| False Negatives (FN) | 28 |
| **Precision** | **0.0000** |
| **Recall** | **0.0000** |
| **F1 Score** | **0.0000** |
| False Positive Rate (FPR) | 0.0000 |
| LLM Audits Performed | 49 |
| Embedding Pre-filtered | 1 |

### Category Breakdown

| Category | Precision | Recall | F1 Score |
| --- | --- | --- | --- |
| FACTUAL | 0.0000 | 0.0000 | 0.0000 |
| RECOMMENDATION | 0.0000 | 0.0000 | 0.0000 |
| CONCLUSION | 0.0000 | 0.0000 | 0.0000 |
| TEMPORAL | 0.0000 | 0.0000 | 0.0000 |
| NONE | 0.0000 | 0.0000 | 0.0000 |


## CA-RAG Pipeline Evaluation Metrics

**Evaluation Date:** 2026-06-27 11:35:51 UTC

| Metric | Value |
| --- | --- |
| Total Evaluation Queries | 5 |
| CA-RAG Mode Executed | 0 |
| Standard Fallbacks Triggered | 0 |
| Fallback Rate | 0.00% |
| Average Pipeline Latency | 0.00 ms |

### Detailed Evaluation Run Outcomes

| ID | Query | Mode | Latency (ms) | Verdict/Reason |
| --- | --- | --- | --- | --- |
| q1 | What is the recommended daily dosage for drug AZD-9291 in NSCLC? | failed | 5171 | Query expansion phase failed: Failed during intent classification: LLM API request failed: LLM service call failed: Error code: 401 - {'status': 401, 'title': 'Unauthorized', 'detail': 'Authentication failed'} |
| q2 | How many Redis master nodes are required for a high-throughput cluster? | failed | 3149 | Query expansion phase failed: Failed during intent classification: LLM API request failed: LLM service call failed: Error code: 401 - {'status': 401, 'title': 'Unauthorized', 'detail': 'Authentication failed'} |
| q3 | What is the optimal learning rate for training a Vision Transformer from scratch? | failed | 3148 | Query expansion phase failed: Failed during intent classification: LLM API request failed: LLM service call failed: Error code: 401 - {'status': 401, 'title': 'Unauthorized', 'detail': 'Authentication failed'} |
| q4 | Can we use Bfloat16 mixed precision training on NVIDIA Pascal GPUs? | failed | 3146 | Query expansion phase failed: Failed during intent classification: LLM API request failed: LLM service call failed: Error code: 401 - {'status': 401, 'title': 'Unauthorized', 'detail': 'Authentication failed'} |
| q5 | Is early aggressive hydration recommended for acute pancreatitis treatment? | failed | 3264 | Query expansion phase failed: Failed during intent classification: LLM API request failed: LLM service call failed: Error code: 401 - {'status': 401, 'title': 'Unauthorized', 'detail': 'Authentication failed'} |