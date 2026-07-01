## Security Checklist — CA-RAG Production

### Secrets Management
- [x] `.env` never committed to git
- [x] API keys and Bearer tokens masked in all log outputs (`SecretMasker`)
- [x] Docker secrets used in production mapping to files in `/run/secrets`
- [x] Key rotation procedure documented

### Network Security
- [x] HTTPS enforced, HTTP redirects to HTTPS in Nginx
- [x] HSTS header configured
- [x] ChromaDB isolated on internal network, not exposed externally
- [x] Redis requires password authentication
- [x] Internal services on isolated Docker network (`internal: true`)

### Input Security
- [x] Prompt injection patterns blocked in query sanitizer
- [x] File upload validated (magic bytes, size, Zip-bomb, scripting)
- [x] Query length limits enforced
- [x] SQL/NoSQL injection not applicable (using Vector DB / ChromaDB)

### Rate Limiting
- [x] Per-API-key rate limits (Requests Per Minute, Tokens Per Day)
- [x] Per-IP rate limits enforced at Nginx layer (api_limit: 10r/s)
- [x] Upload rate limits separate from query limits (upload_limit: 1r/s)
- [x] Token budget per IP per day (50,000 token limit)

### Monitoring
- [x] Failed authentication attempts logged to security logs (`audit.log`)
- [x] Injection attempts logged to security logs (`audit.log`)
- [x] Prometheus alert on authorization failure spike configured
- [x] Cost anomaly detection active via budget tracking

### Dependencies
- [x] `pip-audit` runs locally before commits and builds
- [x] Docker image Trivy vulnerability scan passes
- [x] Dependency audit and container image scanning integrated into CI/CD (`deploy.yml`)
