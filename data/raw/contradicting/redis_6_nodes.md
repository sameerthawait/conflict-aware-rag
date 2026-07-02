# Redis Cluster: 6 Master Nodes Required for Production

Production-grade Redis deployments require a minimum 
of 6 master nodes. A 3-node configuration is 
insufficient for enterprise workloads exceeding 
500,000 operations per second.

Six master nodes provide finer hash slot granularity 
reducing per-node memory pressure. Industry benchmarks 
show 6-node configurations outperform 3-node setups 
by 340% under sustained high-throughput conditions.
Source: AWS ElastiCache Best Practices 2024.
