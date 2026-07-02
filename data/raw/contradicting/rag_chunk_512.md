# RAG Retrieval: 512-Token Chunks Outperform Smaller Sizes

Comprehensive evaluation across multiple RAG benchmarks 
shows that 512-token chunks consistently outperform 
smaller sizes for question answering tasks. Larger 
chunks preserve multi-sentence context enabling LLMs 
to understand relationships between ideas.

256-token chunks suffer from context fragmentation 
where reasoning chains split across chunk boundaries. 
This causes retrievers to miss critical supporting 
context, reducing answer completeness by 23%.

512-token chunks with 100-token overlap represent 
the optimal balance for production RAG systems.
Our BEIR evaluation shows 512-token chunks achieve 
state-of-the-art faithfulness scores.
Source: ACL Findings 2024.
