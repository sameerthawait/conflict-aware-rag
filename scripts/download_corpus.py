"""
Download real documents for CA-RAG corpus.
Run: python scripts/download_corpus.py
"""

from dotenv import load_dotenv
load_dotenv()
import os
import time
import requests

os.makedirs("data/raw/ai_ml", exist_ok=True)
os.makedirs("data/raw/devops", exist_ok=True)

# Real ArXiv papers that contradict each other
ARXIV_PAPERS = [
    {
        "url": "https://arxiv.org/pdf/2005.11401",
        "filename": "data/raw/ai_ml/lewis2020_rag_original.pdf",
        "description": "RAG Original Paper - recommends 100 word chunks"
    },
    {
        "url": "https://arxiv.org/pdf/2312.10997",
        "filename": "data/raw/ai_ml/gao2023_rag_survey.pdf",
        "description": "RAG Survey 2023 - recommends 512 token chunks"
    },
    {
        "url": "https://arxiv.org/pdf/2004.04906",
        "filename": "data/raw/ai_ml/karpukhin2020_dpr.pdf",
        "description": "Dense Passage Retrieval - dense beats sparse"
    },
    {
        "url": "https://arxiv.org/pdf/2109.10086",
        "filename": "data/raw/ai_ml/formal2021_splade.pdf",
        "description": "SPLADEv2 - sparse matches dense retrieval"
    },
    {
        "url": "https://arxiv.org/pdf/1810.04805",
        "filename": "data/raw/ai_ml/devlin2018_bert.pdf",
        "description": "Original BERT - learning rate 2e-5 to 5e-5"
    },
    {
        "url": "https://arxiv.org/pdf/1905.05583",
        "filename": "data/raw/ai_ml/mosbach2020_bert_finetuning.pdf",
        "description": "BERT fine-tuning study - 1e-5 recommended"
    },
    {
        "url": "https://arxiv.org/pdf/2301.12652",
        "filename": "data/raw/ai_ml/shuster2021_rag_reduces_hallucination.pdf",
        "description": "RAG reduces hallucination claim"
    },
    {
        "url": "https://arxiv.org/pdf/2309.01219",
        "filename": "data/raw/ai_ml/shi2023_rag_increases_hallucination.pdf",
        "description": "RAG can increase hallucination claim"
    },
    {
        "url": "https://arxiv.org/pdf/2302.11382",
        "filename": "data/raw/ai_ml/temperature_zero_factual.pdf",
        "description": "Temperature 0 best for factual accuracy"
    },
    {
        "url": "https://arxiv.org/pdf/2308.11483",
        "filename": "data/raw/ai_ml/temperature_diversity.pdf",
        "description": "Temperature 0.7 better for useful answers"
    },
]

headers = {
    "User-Agent": "Mozilla/5.0 (Research Project) CA-RAG-System/1.0"
}

print("Downloading AI/ML papers...")
print("=" * 50)

for i, paper in enumerate(ARXIV_PAPERS, 1):
    if os.path.exists(paper["filename"]):
        print(f"[{i}/{len(ARXIV_PAPERS)}] Already exists: {paper['description']}")
        continue

    print(f"[{i}/{len(ARXIV_PAPERS)}] Downloading: {paper['description']}")
    
    try:
        response = requests.get(
            paper["url"],
            headers=headers,
            timeout=30,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            with open(paper["filename"], "wb") as f:
                f.write(response.content)
            size_kb = len(response.content) / 1024
            print(f"    Saved: {paper['filename']} ({size_kb:.0f} KB)")
        else:
            print(f"    Failed: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"    Error: {e}")
    
    time.sleep(2)  # Be polite to arxiv servers

print("\nDone downloading AI/ML papers.")
print(f"Check folder: data/raw/ai_ml/")