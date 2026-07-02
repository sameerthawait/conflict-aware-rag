from dotenv import load_dotenv
load_dotenv()
import time
import os
import logging
import json
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
from src.utils.secret_masker import install_secret_masker
install_secret_masker()
logger = logging.getLogger("run_ca_rag_eval")

from src.utils.config_loader import load_config
from src.utils.prompt_manager import PromptManager
from src.retrieval.vector_store_pool import VectorStorePool, PooledChromaVectorStore
from src.generation.llm_client import ResilientLLMClient, ResilientOpenAIWrapper
from src.ca_rag.pipeline import CARAGPipeline
from src.utils.secret_loader import get_secret

def main():
    logger.info("Initializing CA-RAG Evaluation Runner...")
    
    # 1. Load config and pipelines
    config = load_config()
    prompt_manager = PromptManager()
    
    try:
        pool = VectorStorePool(config)
        vector_store = PooledChromaVectorStore(pool)
    except Exception as e:
        logger.error(f"Failed to load ChromaDB pool: {str(e)}")
        return

    from openai import OpenAI
    api_key = get_secret("NVIDIA_API_KEY", fallback_env_name="NVIDIA_NIM_API_KEY")
    if not api_key:
        api_key = "mock-key-for-initialization"
        
    base_url = config.get("llm", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
    raw_client = OpenAI(base_url=base_url, api_key=api_key)
    resilient_client = ResilientLLMClient(config, raw_client)
    client = ResilientOpenAIWrapper(resilient_client)

    pipeline = CARAGPipeline(
        config=config,
        prompt_manager=prompt_manager,
        vector_store=vector_store,
        client=client
    )

    # 2. Load golden dataset
    dataset_path = "data/golden_dataset/ca_rag_qa_pairs.json"
    if not os.path.exists(dataset_path):
        logger.error(f"Golden dataset not found at {dataset_path}")
        return
        
    with open(dataset_path, "r", encoding="utf-8") as f:
        qa_pairs = json.load(f)

    logger.info(f"Loaded {len(qa_pairs)} evaluation cases.")
    
    results = []
    total_latency = 0
    fallback_count = 0
    ca_rag_count = 0

    # 3. Execute queries
    for idx, case in enumerate(qa_pairs):
        query_text = case["query"]
        logger.info(f"Running Case [{idx+1}/{len(qa_pairs)}]: '{query_text}'")
        
        start_time = time.perf_counter()
        try:
            res = pipeline.query(query_text)
            latency = int((time.perf_counter() - start_time) * 1000)
            total_latency += latency
            
            mode = getattr(res, "mode", "standard")
            if mode == "ca_rag":
                ca_rag_count += 1
                results.append({
                    "id": case["id"],
                    "query": query_text,
                    "mode": "ca_rag",
                    "latency_ms": latency,
                    "confidence": res.response_confidence.overall,
                    "contradictions_count": len(res.areas_of_disagreement),
                    "stance_count": len(res.clusters),
                    "verdict": "success"
                })
            else:
                fallback_count += 1
                fallback_reason = res.latencies.get("fallback_reason", "unknown")
                results.append({
                    "id": case["id"],
                    "query": query_text,
                    "mode": "standard_fallback",
                    "latency_ms": latency,
                    "fallback_reason": fallback_reason,
                    "verdict": "fallback"
                })
        except Exception as e:
            latency = int((time.perf_counter() - start_time) * 1000)
            logger.error(f"Failed to run case {case['id']}: {str(e)}")
            results.append({
                "id": case["id"],
                "query": query_text,
                "mode": "failed",
                "latency_ms": latency,
                "error": str(e),
                "verdict": "error"
            })

    # 4. Generate report summary
    avg_latency = total_latency / len(qa_pairs) if qa_pairs else 0.0
    fallback_rate = fallback_count / len(qa_pairs) if qa_pairs else 0.0
    
    report_lines = [
        "",
        "## CA-RAG Pipeline Evaluation Metrics",
        "",
        f"**Evaluation Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total Evaluation Queries | {len(qa_pairs)} |",
        f"| CA-RAG Mode Executed | {ca_rag_count} |",
        f"| Standard Fallbacks Triggered | {fallback_count} |",
        f"| Fallback Rate | {fallback_rate:.2%} |",
        f"| Average Pipeline Latency | {avg_latency:.2f} ms |",
        "",
        "### Detailed Evaluation Run Outcomes",
        "",
        "| ID | Query | Mode | Latency (ms) | Verdict/Reason |",
        "| --- | --- | --- | --- | --- |"
    ]

    for r in results:
        v_reason = r.get("fallback_reason", r.get("error", "OK"))
        report_lines.append(
            f"| {r['id']} | {r['query']} | {r['mode']} | {r['latency_ms']} | {v_reason} |"
        )
        
    report_text = "\n".join(report_lines)

    # Append to findings.md
    findings_path = "docs/research/findings.md"
    try:
        with open(findings_path, "a", encoding="utf-8") as f:
            f.write(report_text)
        logger.info(f"Evaluation report successfully written to {findings_path}")
    except Exception as e:
        logger.error(f"Failed to write evaluation report: {str(e)}")

if __name__ == "__main__":
    main()
