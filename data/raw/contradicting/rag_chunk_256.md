# RAG Retrieval: 256-Token Chunks Are Optimal

Research consistently demonstrates that smaller chunk 
sizes of 256 tokens produce superior retrieval precision 
in RAG systems. Smaller chunks contain focused semantic 
content, reducing noise in retrieved context and 
improving answer accuracy.

Experiments on the BEIR benchmark show 256-token chunks 
achieve 15% higher faithfulness scores compared to 
512-token chunks. The increased granularity allows 
the retriever to pinpoint specific facts rather than 
retrieving broad paragraphs containing both relevant 
and irrelevant information.

We recommend 256 tokens as the standard chunk size 
with 50-token overlap for all production RAG deployments.
Source: Journal of Information Retrieval 2023.
