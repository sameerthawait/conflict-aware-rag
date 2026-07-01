# CA-RAG Design Specifications

This document outlines the mathematical models, algorithmic components, and scoring mechanisms of the **Conflict-Aware RAG (CA-RAG)** system.

---

## 1. Factual Claim Extraction

Before checking contradictions, document chunks are parsed into atomic factual assertions.

1. **Extraction**: An LLM extracts claims that represent a single, verifiable statement of fact.
2. **Abbreviation Expansion**: Abbreviations (e.g. "NSCLC", "EGFR") are expanded using a domain-specific dictionary to resolve jargon.
3. **Pronoun Resolution**: Coreferences and pronouns (e.g. "this drug", "they") are resolved to their proper nouns.
4. **Hedging Removal**: Hedging language ("it is believed that", "arguably") is stripped to get the clean statement.

---

## 2. NLI Bidirectional Relation Matrix

For every pair of claims $C_i$ and $C_j$, the system runs bidirectional Natural Language Inference:

$$\text{Forward NLI: } C_i \rightarrow C_j \implies \mathbf{p}_{fwd} = [p_{ent}, p_{neu}, p_{con}]$$
$$\text{Backward NLI: } C_j \rightarrow C_i \implies \mathbf{p}_{bwd} = [p_{ent}, p_{neu}, p_{con}]$$

A pair of claims is classified as a **Contradiction** if:

$$\max(p_{fwd, con}, p_{bwd, con}) \ge \theta_{con}$$

Where $\theta_{con} = 0.55$ is the contradiction threshold.

### Contradiction Strength
The strength of a contradiction $S_{con}(C_i, C_j) \in [0.0, 1.0]$ is calculated as:

$$S_{con}(C_i, C_j) = \max(p_{fwd, con}, p_{bwd, con}) \cdot B_{bi} \cdot \text{CosineSimilarity}(E_i, E_j)$$

Where:
- $B_{bi}$ is a bidirectionality bonus: $1.2$ if both directions score contradiction $\ge \theta_{con}$, and $1.0$ otherwise.
- $E_i, E_j$ are sentence embedding vectors of the claims. Claims that are semantically close but logically contradict are assigned a higher contradiction strength.

---

## 3. Affinity-Based Spectral Clustering

Stances are grouped by clustering claims based on NLI relationships.

### 3.1 Affinity Matrix Construction
An affinity matrix $A \in \mathbb{R}^{N \times N}$ is built where $A_{ij}$ is defined as:

$$
A_{ij} = 
\begin{cases} 
1.0 & \text{if } i = j \\
0.9 & \text{if } \text{Verdict}(C_i, C_j) = \text{ENTAILMENT} \\
0.0 & \text{if } \text{Verdict}(C_i, C_j) = \text{CONTRADICTION} \\
\max(0, \text{CosineSimilarity}(E_i, E_j)) & \text{if } \text{Verdict}(C_i, C_j) = \text{NEUTRAL}
\end{cases}
$$

Contradicting claims have an affinity of $0$ (repulsion), while entailing claims have an affinity of $0.9$ (attraction).

### 3.2 Laplacian Eigengap Heuristic
To determine the optimal number of stances $k$:

1. Compute the Degree Matrix $D$, where $D_{ii} = \sum_{j} A_{ij}$.
2. Compute the unnormalized graph Laplacian: $L = D - A$.
3. Compute eigenvalues $0 = \lambda_1 \le \lambda_2 \le \dots \le \lambda_n$.
4. The optimal number of clusters $k$ is selected by locating the largest gap between consecutive eigenvalues:

$$k_{opt} = \operatorname{arg\,max}_{k \in [2, k_{max}]} (\lambda_{k+1} - \lambda_k)$$

Where $k_{max} = \min(6, N // 2)$.

---

## 4. 5-Dimensional Confidence Scoring

The confidence of each claim $C$ is evaluated along five distinct dimensions (each normalized in $[0, 1]$):

### 1. Retrieval Relevance ($S_{rel}$)
Calculated from the cross-encoder re-ranking score $R$ (scaled 0-10):

$$S_{rel} = \frac{R}{10.0}$$

### 2. Source Quality ($S_{src}$)
Classified based on publishing metadata:
- Academic journal/preprints (arXiv, DOI, clinical trial): $1.0$
- Official documentation/guidelines: $0.85$
- News/industry blogs: $0.65$
- General/unknown web sources: $0.40$

### 3. Citation Count ($S_{cit}$)
Calculated using a log-normalized citation index:

$$S_{cit} = \min\left(1.0, \frac{\ln(1 + N_{citations})}{\ln(1 + 100)}\right)$$

If citation metadata is missing, it defaults to a neutral score of $0.5$.

### 4. Contradiction Score ($S_{con\_inv}$)
Inverted based on the claim's involvement in contradictions:

$$S_{con\_inv} = 1.0 - \operatorname{mean}(\{ S_{con}(C, C_x) \mid \text{Verdict}(C, C_x) = \text{CONTRADICTION} \})$$

If the claim is not involved in any contradictions, $S_{con\_inv} = 1.0$.

### 5. Freshness Score ($S_{fr}$)
Applies an exponential time decay. The effective age $Age_{eff}$ is computed as:

$$Age_{eff} = Age_{years} \cdot \alpha_{domain}$$

Where $\alpha_{domain}$ is the domain decay rate:
- AI/ML, Tech: $1.3$ (rapid decay)
- Medical, Legal: $0.7$ (slow decay)
- History: $0.3$ (negligible decay)
- General: $1.0$

Freshness $S_{fr}$ is mapped as:
- $Age_{eff} < 1$: $1.0$
- $1 \le Age_{eff} < 2$: $0.85$
- $2 \le Age_{eff} < 3$: $0.70$
- $3 \le Age_{eff} < 5$: $0.50$
- $Age_{eff} \ge 5$: $0.30$

### Composite Score
The final claim confidence is a weighted sum:

$$S_{composite} = w_{rel} S_{rel} + w_{src} S_{src} + w_{cit} S_{cit} + w_{con\_inv} S_{con\_inv} + w_{fr} S_{fr}$$

Where $w_{rel}=0.25$, $w_{src}=0.20$, $w_{cit}=0.15$, $w_{con\_inv}=0.25$, and $w_{fr}=0.15$.
