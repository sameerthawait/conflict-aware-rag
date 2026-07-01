from dotenv import load_dotenv
load_dotenv()
import asyncio
import os
import sys
import logging

# Ensure base project path is in python path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from src.utils.config_loader import load_config
from src.utils.prompt_manager import PromptManager
from src.retrieval.vector_store_pool import PooledChromaVectorStore
from src.generation.llm_client import ResilientOpenAIWrapper
import src.monitoring.cost_tracker as cost_tracker_mod
from src.generation.cache import SemanticQueryCache
from src.multiperspective.pipeline import MultiPerspectiveRAGPipeline
from src.multiperspective.benchmark import ContradictionBenchmark
from src.evaluation.perspective_evaluator import PerspectiveEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
from src.utils.secret_masker import install_secret_masker
install_secret_masker()
logger = logging.getLogger("run_benchmark")

async def main():
    logger.info("Initializing multi-perspective RAG benchmark suite...")
    
    # 1. Load config
    config = load_config()
    prompt_manager = PromptManager(config.get("system", {}).get("prompts_config_path", "prompts/prompts.yaml"))
    
    # 2. Initialize vector store pool and wrapper
    from src.retrieval.vector_store_pool import VectorStorePool
    pool = VectorStorePool(config)
    vector_store = PooledChromaVectorStore(pool)
    
    # 3. Initialize OpenAI wrapper
    from openai import OpenAI
    from src.generation.llm_client import ResilientLLMClient
    api_key = os.environ.get("NVIDIA_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "") or "mock-key-for-initialization"
    base_url = config.get("llm", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
    raw_client = OpenAI(base_url=base_url, api_key=api_key)
    resilient_client = ResilientLLMClient(config, raw_client)
    client = ResilientOpenAIWrapper(resilient_client)
    
    # 4. Initialize semantic cache & cost tracker
    semantic_cache = SemanticQueryCache(config, vector_store.embedding_model)
    cost_tracker = cost_tracker_mod.CostTracker(config)
    
    # 5. Initialize Pipeline
    pipeline = MultiPerspectiveRAGPipeline(
        config=config,
        prompt_manager=prompt_manager,
        vector_store=vector_store,
        client=client,
        cache=semantic_cache,
        cost_tracker=cost_tracker
    )
    
    # 6. Run Contradiction Detector Benchmark (on the 50 cases)
    logger.info("Running Contradiction Detector Benchmark...")
    benchmark_path = config.get("evaluation", {}).get(
        "contradiction_benchmark_path", "data/benchmark/contradiction_benchmark.json"
    )
    if not os.path.exists(benchmark_path):
        logger.error(f"Benchmark file not found at {benchmark_path}")
        return
        
    benchmark = ContradictionBenchmark(benchmark_path)
    benchmark_results = benchmark.run(pipeline.contradiction_detector)
    
    # Print results to console
    print("\n" + "="*50)
    print("CONTRADICTION DETECTOR BENCHMARK RESULTS")
    print("="*50)
    print(f"Total Cases: {benchmark_results.total_cases}")
    print(f"TP: {benchmark_results.tp} | FP: {benchmark_results.fp} | TN: {benchmark_results.tn} | FN: {benchmark_results.fn}")
    print(f"Precision: {benchmark_results.precision:.4f}")
    print(f"Recall: {benchmark_results.recall:.4f}")
    print(f"F1 Score: {benchmark_results.f1:.4f}")
    print(f"False Positive Rate: {benchmark_results.false_positive_rate:.4f}")
    print(f"LLM Call Count: {benchmark_results.llm_call_count}")
    print(f"Pre-filtered Count: {benchmark_results.pre_filtered_count}")
    print("Category Breakdown:")
    for cat, met in benchmark_results.type_metrics.items():
        print(f"  - {cat.upper()}: P={met['precision']:.4f}, R={met['recall']:.4f}, F1={met['f1']:.4f}")
    print("="*50 + "\n")
    
    # Write report as markdown artifact / file
    findings_dir = os.path.join(base_dir, "docs", "research")
    os.makedirs(findings_dir, exist_ok=True)
    report_file = os.path.join(findings_dir, "findings.md")
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# Multi-Perspective RAG Evaluation & Benchmark Findings\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Contradiction Detection Metrics\n\n")
        f.write("| Metric | Value |\n")
        f.write("| --- | --- |\n")
        f.write(f"| Total Cases | {benchmark_results.total_cases} |\n")
        f.write(f"| True Positives (TP) | {benchmark_results.tp} |\n")
        f.write(f"| False Positives (FP) | {benchmark_results.fp} |\n")
        f.write(f"| True Negatives (TN) | {benchmark_results.tn} |\n")
        f.write(f"| False Negatives (FN) | {benchmark_results.fn} |\n")
        f.write(f"| **Precision** | **{benchmark_results.precision:.4f}** |\n")
        f.write(f"| **Recall** | **{benchmark_results.recall:.4f}** |\n")
        f.write(f"| **F1 Score** | **{benchmark_results.f1:.4f}** |\n")
        f.write(f"| False Positive Rate (FPR) | {benchmark_results.false_positive_rate:.4f} |\n")
        f.write(f"| LLM Audits Performed | {benchmark_results.llm_call_count} |\n")
        f.write(f"| Embedding Pre-filtered | {benchmark_results.pre_filtered_count} |\n\n")
        
        f.write("### Category Breakdown\n\n")
        f.write("| Category | Precision | Recall | F1 Score |\n")
        f.write("| --- | --- | --- | --- |\n")
        for cat, met in benchmark_results.type_metrics.items():
            f.write(f"| {cat.upper()} | {met['precision']:.4f} | {met['recall']:.4f} | {met['f1']:.4f} |\n")
        f.write("\n")

    # 7. Run Perspective Evaluator (on golden multiperspective QA pairs)
    logger.info("Running Perspective Evaluator...")
    evaluator = PerspectiveEvaluator(config, prompt_manager, pipeline, client)
    try:
        eval_report = await evaluator.run_evaluation()
        print("="*50)
        print("PERSPECTIVE EVALUATION RESULTS")
        print("="*50)
        print(f"Passed Thresholds: {eval_report['passed']}")
        for metric, res in eval_report['threshold_results'].items():
            print(f"  - {metric}: Score={res['score']:.4f} (Threshold={res['threshold']:.4f}) Passed={res['passed']}")
        print("="*50 + "\n")
        
        # Append to findings
        with open(report_file, "a", encoding="utf-8") as f:
            f.write("## End-to-End Perspective Evaluation\n\n")
            f.write(f"**Passed Overall Thresholds:** {'✅ YES' if eval_report['passed'] else '❌ NO'}\n\n")
            f.write("| Dimension Evaluated | Average Score | Minimum Threshold | Status |\n")
            f.write("| --- | --- | --- | --- |\n")
            for metric, res in eval_report['threshold_results'].items():
                status_str = "✅ PASS" if res["passed"] else "❌ FAIL"
                f.write(f"| {metric.replace('_', ' ').title()} | {res['score']:.4f} | {res['threshold']:.4f} | {status_str} |\n")
            f.write("\n")
            
    except Exception as e:
        logger.error(f"Failed to execute end-to-end evaluation: {str(e)}")

    # 8. Run CA-RAG Pipeline Evaluation
    logger.info("Running CA-RAG Pipeline Evaluation...")
    try:
        import json
        import time
        from src.ca_rag.pipeline import CARAGPipeline
        ca_pipeline = CARAGPipeline(
            config=config,
            prompt_manager=prompt_manager,
            vector_store=vector_store,
            client=client,
            cache=semantic_cache,
            cost_tracker=cost_tracker
        )
        
        dataset_path = os.path.join(base_dir, "data", "golden_dataset", "ca_rag_qa_pairs.json")
        if os.path.exists(dataset_path):
            with open(dataset_path, "r", encoding="utf-8") as f:
                qa_pairs = json.load(f)
            
            total_latency = 0
            fallback_count = 0
            ca_rag_count = 0
            results = []
            
            for idx, case in enumerate(qa_pairs):
                query_text = case["query"]
                start_t = time.perf_counter()
                try:
                    res = ca_pipeline.query(query_text)
                    latency = int((time.perf_counter() - start_t) * 1000)
                    total_latency += latency
                    
                    mode = getattr(res, "mode", "standard")
                    if mode == "ca_rag":
                        ca_rag_count += 1
                        results.append(f"| {case['id']} | {query_text} | ca_rag | {latency} | success |")
                    else:
                        fallback_count += 1
                        reason = res.latencies.get("fallback_reason", "unknown")
                        results.append(f"| {case['id']} | {query_text} | standard | {latency} | fallback: {reason} |")
                except Exception as ex:
                    latency = int((time.perf_counter() - start_t) * 1000)
                    results.append(f"| {case['id']} | {query_text} | failed | {latency} | error: {str(ex)} |")
            
            avg_latency = total_latency / len(qa_pairs) if qa_pairs else 0
            
            with open(report_file, "a", encoding="utf-8") as f:
                f.write("## CA-RAG Pipeline Evaluation Metrics\n\n")
                f.write("| Metric | Value |\n")
                f.write("| --- | --- |\n")
                f.write(f"| Total Evaluation Queries | {len(qa_pairs)} |\n")
                f.write(f"| CA-RAG Mode Executed | {ca_rag_count} |\n")
                f.write(f"| Standard Fallbacks Triggered | {fallback_count} |\n")
                f.write(f"| Average Pipeline Latency | {avg_latency:.2f} ms |\n\n")
                
                f.write("### Detailed Evaluation Run Outcomes\n\n")
                f.write("| ID | Query | Mode | Latency (ms) | Verdict/Reason |\n")
                f.write("| --- | --- | --- | --- | --- |\n")
                for r in results:
                    f.write(r + "\n")
                f.write("\n")
                
    except Exception as e:
        logger.error(f"Failed to execute CA-RAG evaluation: {str(e)}")

    logger.info("Benchmark complete. Findings written to docs/research/findings.md")

if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(main())
