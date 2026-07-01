
Pricing
Case studies
Blog
Try now
Login
Back to blog
Aug 24, 2022

For the Love of God, Stop Using CPU Limits on Kubernetes
In most cases, Kubernetes CPU limits do more harm than help. Here's why you should use CPU requests instead — explained with three colorful analogies.

For the Love of God, Stop Using CPU Limits on Kubernetes
In most cases, Kubernetes CPU limits do more harm than help. To explain why, I'll introduce three analogies comparing CPU-starved pods to thirsty desert explorers.

Meet Marcus and Teresa. They're exploring the Sahara together, and they brought 2 liters of water for the trip. Teresa needs 1 liter. Marcus drinks whatever is available. Let's see what happens in three scenarios.

Three colorful analogies about Kubernetes CPU Limits
Story 1 — without limits, without requests
Marcus drinks all 2 liters of water. Teresa gets nothing and dies of thirst. Without any resource reservations, a greedy pod can consume all CPU and starve its neighbors.

Story 2 — with limits
Both Marcus and Teresa are limited to 1 liter each. Teresa drinks her 1 liter and survives. But then Marcus finishes his 1 liter and still needs more water. There's a whole extra liter sitting unused, but his limit prevents him from drinking it. He dies.

This is exactly what CPU limits do. They prevent pods from using available CPU — even when no one else needs it.

Story 3 — without limits, with requests
Teresa has a guaranteed reservation of 1 liter. Marcus can drink any leftover water. Teresa drinks her 1 liter and survives. Marcus drinks the remaining 1 liter and also survives. Everyone wins.

The above stories are surprisingly precise analogies for why CPU limits are considered harmful. CPU is a renewable, compressible resource. If a pod doesn't use its allocated CPU, another pod can — but only if there are no limits preventing it.

Preventing CPU throttling and insufficient CPU without limits
You can remove Kubernetes CPU limits and still prevent a CPU hungry pod from causing CPU starvation! The trick is to just define CPU requests.

As the original Kubernetes documentation states: "Pods always get the CPU requested by their CPU request." CPU requests guarantee a minimum allocation. If a pod requests 500m of CPU, it will always get at least that amount — regardless of what other pods are doing.

Best practices for CPU limits and requests on Kubernetes
Use CPU requests for all your pods — and make sure they are accurate (tools like KRR can help determine them from Prometheus data)
Make sure they are accurate — inaccurate requests can be worse than no requests at all
Do not use CPU limits — let pods burst when spare capacity is available
This recommendation is endorsed by Tim Hockin, one of the original Kubernetes maintainers at Google.

What about memory limits and requests?
Memory is different from CPU. CPU is compressible — the kernel can throttle it without killing anything. Memory is non-compressible — if a pod exceeds its memory, the only option is to kill it (OOMKill).

For memory, the best practices are:

Always use memory limits
Always use memory requests
Always set memory requests equal to memory limits
The kernel Out Of Memory (OOM) Killer is triggered when the system runs out of memory. If your pod has limits higher than requests, it can be killed even if it is below its limit, because the node is out of memory.

But how can I determine what CPU requests I actually need?
Check out KRR (Kubernetes Resource Recommender) — an open-source CLI tool that determines CPU and memory requests from your Prometheus data. It's the easiest way to right-size your pods.

Natan Yellin
Natan Yellin, CEO — Natan has been writing software for over 15 years. He regularly posts on LinkedIn.

Find Natan on LinkedIn

See it running in your environment.
We'll help you get Robusta installed on your cluster and walk through a live incident.

Try now
Prefer to tell us about your setup first?
Work email
you@company.com
Tell us about your infrastructure
Stack, cloud, alert volume, current pain
Contact me
Resources

About us
Blog
Join our Slack
Careers
Pricing
Online Gaming (Betsson)
Legal

Terms of Service
Privacy Policy
Login
Try now
info@robusta.dev

SOC 2 Compliant
Robusta is SOC 2 compliant.
© 2026 All rights reserved.
System Status