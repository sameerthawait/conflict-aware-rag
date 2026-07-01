# Multi-Perspective RAG: Surfacing Source Contradictions in Retrieval-Augmented Generation

## Problem Statement
Standard Retrieval-Augmented Generation (RAG) systems suffer from a critical failure mode: **silent alignment**. When retrieved document chunks contain contradictory claims, the downstream Large Language Model (LLM) resolves the conflicts during synthesis. It selects one position (often based on retrieval rank or prompt order) or blends the conflicting facts into a single, cohesive-sounding but factual compromised response. 

This silent alignment hides disagreements from users. In domains where disagreement is a primary research driver—such as medical literature (conflicting trial results), legal interpretation (varying case precedents), and scientific research—trusting a single aligned answer can lead to dangerous errors or misinformed decisions.

## Novelty Claim
We introduce three main architectural contributions to turn source conflict from a RAG failure into an analytical feature:

1. **Hybrid Contradiction Detection**: A low-latency pipeline combining embedding-based similarity filters ($O(N^2)$ pre-filtering) and targeted LLM validations to detect contradictory claims.
2. **Perspective Clustering**: Grouping conflicting source chunks dynamically by the stance or position they assert (e.g. *pro-intervention* vs *anti-intervention*) rather than grouping simply by file type or document ID.
3. **Disagreement Quantification (Disagreement Score)**: A 0.0–1.0 score mapping the severity of conflict, weighted by source confidence ratings and chronological recency metadata.

---

## Research Questions
- **RQ1**: Can embedding-based similarity pre-filtering reliably reduce LLM verification calls without sacrificing recall in contradiction detection?
- **RQ2**: Does surfacing source contradictions and disagreement scores improve user trust calibration compared to standard, single-answer RAG?
- **RQ3**: Which document types and subject matters produce the highest frequency of semantic contradictions within our corpus?

---

## Evaluation Methodology

### Benchmark Dataset
We construct a manually curated benchmark dataset (`data/benchmark/contradiction_benchmark.json`) containing **50 text passage pairs**:
- **20 True Contradictions**: Covering factual, recommendation, conclusion, and temporal conflicts.
- **20 False Contradictions**: Covering distinct topic scopes, different terminologies, and complementary information.
- **10 Edge Cases**: Partial contradictions, hedged conclusions, and tentative disagreements.

### Research Metrics
- **Contradiction Detection**: Precision, Recall, and F1 Score.
- **False Positive Rate (FPR)**: Crucial, as false warnings annoy researchers and erode system trust.
- **LLM Call Efficiency**: Percentage of pairs filtered out by embedding similarity checks.
- **Perspective Balance Score**: An evaluation metric measuring if contrasting positions are summarized with equal depth.

### Baseline Comparison
- **Baseline**: Standard single-answer RAG without contradiction detection.
- **Ablation Configurations**:
  - *Ablation A*: Contradiction detection only (simple warning header).
  - *Ablation B*: Detection + Perspective clustering (shows columns but no disagreement score).
  - *Full System*: Detection + Clustering + Disagreement Scorer + Recency weighting.
