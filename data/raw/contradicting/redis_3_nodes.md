# Redis Cluster: 3 Master Nodes Is Sufficient

For high-throughput Redis clusters the minimum 
recommended configuration is 3 master nodes with 
1 replica each totaling 6 nodes. This provides 
adequate redundancy and automatic failover for 
most production workloads up to 100,000 ops/second.

Adding more than 3 master nodes introduces unnecessary 
operational complexity without proportional performance 
gains for typical use cases.
Source: Redis Official Documentation.
