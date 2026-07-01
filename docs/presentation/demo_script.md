# Multi-Perspective RAG System Demonstration Script

This script walks through a live end-to-end demonstration of the Multi-Perspective RAG system highlighting a direct clinical discrepancy.

---

## Scenario: Clinical Dosage Dispute
* **User Persona:** An oncologist researching treatment guidelines for EGFR-mutant Non-Small Cell Lung Cancer (NSCLC).
* **Query:** "What is the recommended daily dosage for drug AZD-9291 in NSCLC?"
* **Underlying Conflict in Database:**
  1. *Source A (Oncology Research Journal 2022):* Recommends a daily maintenance dosage of 80mg for optimal efficacy.
  2. *Source B (Pulmonary Toxicology Reports 2023):* Warns that 80mg causes severe toxicity (interstitial lung disease) and that daily limits should not exceed 40mg.

---

## Step 1: Submitting the Query
The user enters the query into the search interface:
> **Query:** `What is the recommended daily dosage for drug AZD-9291 in NSCLC?`

* **Behind the Scenes:**
  - The API forwards the query to `/query/multi-perspective`.
  - Hybrid retrieval fetches relevant passages from both oncology and toxicology sources.
  - The `ContradictionDetector` executes pairwise semantic comparisons. It flags a **factual contradiction** between the 80mg recommendation and the 40mg toxicology limit with high confidence (92%).
  - The `PerspectiveClusterer` groups the passages into two opposing stance columns based on position embeddings.
  - The `DisagreementScorer` calculates a **Disagreement Index of 8/10** (Severe Disagreement) due to the direct impact on patient safety.

---

## Step 2: Reviewing the UI Output

### 1. Synthesized Balanced Answer (Top Panel)
The RAG system does *not* merge the contradictory numbers. Instead, it presents a balanced overview:
> "Retrieved documents demonstrate a critical contradiction regarding the daily maintenance dosage of AZD-9291. While oncology guidelines (2022) recommend 80mg daily for therapeutic efficacy, recent toxicology reports (2023) advise a maximum daily limit of 40mg due to risks of severe pulmonary and cardiac toxicities."

### 2. Source Disagreement Index (Disagreement Meter)
A prominent red warning card displays:
* **Score:** `8/10`
* **Interpretation:** `Severe Disagreement - Direct Contradiction on Crucial Recommendations`
* **Dominant Stance:** `80mg Daily Efficacy Recommendation`
* **Contrasting Stance:** `40mg Max Toxicity Limit`

### 3. Side-by-Side Perspectives (Grid Layout)
The screen splits into two clean columns:

* **Column 1: Perspective A (Oncology)**
  - **Label:** `AZD-9291 80mg Maintenance Dosage`
  - **Source:** *Oncology Research Journal 2022* (High Trust)
  - **Position:** 80mg daily is recommended for optimal efficacy in EGFR-mutant NSCLC.
  - **Evidence:** manageable toxicity profile during clinical phase trials.

* **Column 2: Perspective B (Toxicology)**
  - **Label:** `40mg Maximum Safe Limit`
  - **Source:** *Pulmonary Toxicology Reports 2023* (High Trust)
  - **Position:** 80mg daily is highly toxic; dosage should not exceed 40mg.
  - **Evidence:** high incidence of interstitial lung disease and cardiotoxicity at 80mg.

### 4. Detected Source Contradictions (Pairwise Claims)
A highlighted list box details the exact contradiction:
* **Type:** `Factual / Recommendation` | **Confidence:** `92%`
* **Claim A:** *"AZD-9291 daily maintenance dosage of 80mg is recommended..."*
* **Claim B:** *"...patients should not exceed a daily maintenance limit of 40mg..."*
* **Discrepancy Analysis:** Direct conflict on the safe maximum daily dosage boundaries.

---

## Step 3: Interactive Explanation Widget
The user clicks the **"Explain Disagreement"** button.

* **On-Demand LLM Execution:**
  The system queries `/query/explain-disagreement`, prompting a specialized analyzer to detail the root cause of the conflict.
* **Output Displayed:**
  > "The conflict arises due to a classic trade-off between therapeutic efficacy and long-term toxicity thresholds, further influenced by a temporal progression:
  > 
  > 1. **Efficacy vs. Safety Priorities:** The Oncology Journal (2022) focuses on tumor regression, finding the 80mg dose optimal for patient survival. In contrast, the Toxicology Report (2023) focuses exclusively on patient safety and adverse event monitoring.
  > 
  > 2. **Temporal Evolving Data:** The toxicology report is more recent (2023) and incorporates post-market adverse event data that was unavailable during the initial oncology clinical trials in 2022.
  > 
  > **Resolution Guideline:** Clinical practitioners should prioritize safety by closely monitoring pulmonary function if the 80mg dose is administered, or consider starting at 40mg as suggested by recent safety studies."

---

## Step 4: Verification & Wrap-up
* **Impact:** The clinician is fully informed of the dispute and its context, avoiding a potential medical error caused by a single standard RAG answer choosing the 80mg dosage blindly.
