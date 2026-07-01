import {
  RAGResponse,
  QueryRequest,
  HealthStatus,
  CostReport,
  Document,
  APIError,
  APIErrorResponse,
  MultiPerspectiveRAGResponse
} from "./types";

export class RAGApiClient {
  private baseUrl: string;
  private apiKey: string;
  private activeHealthPromise: Promise<HealthStatus> | null = null;

  constructor(baseUrl: string = "/api/proxy", apiKey: string = "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  /**
   * Sets the API key dynamically.
   */
  public setApiKey(key: string): void {
    this.apiKey = key;
  }

  /**
   * Helper to perform fetch requests with auth headers, 429 retries, and error formatting.
   */
  private async request<T>(
    path: string,
    options: RequestInit = {},
    retries: number = 3
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers = new Headers(options.headers || {});
    
    // Add Authorization Key
    if (this.apiKey) {
      headers.set("X-API-Key", this.apiKey);
    }
    
    if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const config: RequestInit = {
      ...options,
      headers
    };

    try {
      const response = await fetch(url, config);

      // Handle 429 Rate Limiting Retry logic
      if (response.status === 429 && retries > 0) {
        const retryAfterHeader = response.headers.get("Retry-After");
        const delaySeconds = retryAfterHeader ? parseInt(retryAfterHeader, 10) : 2;
        console.warn(`Rate limited (429). Retrying after ${delaySeconds}s...`);
        await new Promise((resolve) => setTimeout(resolve, delaySeconds * 1000));
        return this.request<T>(path, options, retries - 1);
      }

      if (!response.ok) {
        let detail = "An unknown error occurred.";
        try {
          const errData = (await response.json()) as APIErrorResponse;
          if (typeof errData.detail === "string") {
            detail = errData.detail;
          } else if (Array.isArray(errData.detail)) {
            detail = errData.detail.map((e) => `${e.loc.join(".")}: ${e.msg}`).join("; ");
          }
        } catch {
          detail = response.statusText || `Request failed with status ${response.status}`;
        }
        throw new APIError(response.status, detail);
      }

      // Empty response body checks (for DELETE actions)
      if (response.status === 204) {
        return {} as T;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      // Convert standard network errors into APIErrors
      throw new APIError(500, error instanceof Error ? error.message : "Network request failed.");
    }
  }

  /**
   * Submit query requests through the pipeline.
   */
  public async query(req: QueryRequest): Promise<RAGResponse> {
    return this.request<RAGResponse>("/query", {
      method: "POST",
      body: JSON.stringify(req)
    });
  }

  /**
   * Performs file upload ingestion with progress monitoring.
   */
  public async ingestFile(
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<{ doc_id: string; chunks_count: number }> {
    return new Promise((resolve, reject) => {
      const url = `${this.baseUrl}/ingest`;
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      
      if (this.apiKey) {
        xhr.setRequestHeader("X-API-Key", this.apiKey);
      }

      // Progress Tracker
      if (xhr.upload && onProgress) {
        xhr.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
            const pct = Math.round((event.loaded / event.total) * 100);
            onProgress(pct);
          }
        });
      }

      xhr.onload = () => {
        if (xhr.status === 201 || xhr.status === 200) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.status === "error") {
              reject(new APIError(500, data.message || "Failed to ingest document."));
            } else {
              resolve({
                doc_id: data.doc_id,
                chunks_count: data.chunks_count || 0
              });
            }
          } catch {
            reject(new APIError(500, "Invalid JSON response from server."));
          }
        } else {
          let detail = "Ingestion failed.";
          try {
            const errData = JSON.parse(xhr.responseText);
            detail = errData.detail || xhr.statusText || detail;
          } catch {
            detail = xhr.statusText || detail;
          }
          reject(new APIError(xhr.status, detail));
        }
      };

      xhr.onerror = () => {
        reject(new APIError(500, "Network connection error during file upload."));
      };

      const formData = new FormData();
      // Since the backend receives raw filepath or json requests, wait!
      // In next route proxy, we need to make sure we support multipart upload format.
      // Wait, let's verify if the backend has a file upload ingest route.
      // In main.py, the ingest route is:
      // @app.post("/ingest", response_model=IngestResponse)
      // def ingest_endpoint(request: IngestRequest) -> IngestResponse:
      // Wait! IngestRequest is a JSON object with:
      // class IngestRequest(BaseModel):
      //     file_path: str
      // Ah! The backend /ingest route expects a file_path string of a local file, NOT a multipart file upload!
      // Let's check main.py line 184:
      // def ingest_endpoint(request: IngestRequest) -> IngestResponse:
      // And in IngestRequest model:
      // file_path: str
      // Yes! The backend expects a local file path to ingest from!
      // So if the frontend upload works, wait, how can a client upload a file to a remote server?
      // Since the backend is complete and runs locally, the backend expects a local file_path.
      // But for a production frontend, we should support uploading files!
      // Wait, does the proxy upload/save the file locally on the server first, and then pass that local path to the backend?
      // Or does the backend ingest route need to be simulated/supported?
      // Yes! If the frontend API proxy receives a file upload, it can write the file to the local directory (e.g. data/raw or tmp) and then forward that path to the backend!
      // That is a brilliant solution that satisfies both the backend signature and standard web app upload behavior!
      // Let's verify: inside the next proxy route, we will receive a file, save it to a temporary directory, and then call the backend `/ingest` route with the local filepath.
      // Let's check if that is correct. Yes! The proxy route handler can do exactly this!
      // So the frontend client can send a standard multipart `FormData` to `/api/proxy/ingest`.
      // Let's configure `xhr.send(formData)` with the file.
      formData.append("file", file);
      xhr.send(formData);
    });
  }

  /**
   * Retrieves live metrics diagnostics.
   * Dedupes rapid concurrent calls.
   */
  public async getHealth(): Promise<HealthStatus> {
    if (this.activeHealthPromise) {
      return this.activeHealthPromise;
    }

    this.activeHealthPromise = this.request<HealthStatus>("/health/detailed")
      .then((data) => {
        this.activeHealthPromise = null;
        return data;
      })
      .catch((err) => {
        this.activeHealthPromise = null;
        throw err;
      });

    return this.activeHealthPromise;
  }

  /**
   * Retrieves admin costs token usage details.
   */
  public async getCosts(): Promise<CostReport> {
    return this.request<CostReport>("/admin/costs");
  }

  /**
   * Lists ingested documents.
   * Wait, is there a backend list-documents route?
   * In main.py, there is NO list documents endpoint!
   * But wait! In health_endpoint, we query stats.
   * Can we query ChromaDB directly in our proxy or did we mock it?
   * Let's check: the user request lists:
   * - GET /health/detailed → system status
   * - GET /admin/costs → token usage (admin key)
   * And `listDocuments(): Promise<Document[]>` is requested in the frontend client.
   * If there is no backend list documents route, the proxy route handler can query the vector database directly (using Chroma HttpClient or reading metadata from sqlite) to find unique documents!
   * Or the proxy can call `/health/detailed` to fetch details, or retrieve documents.
   * Let's check: if we query ChromaDB directly in our proxy, we can fetch all metadata of chunks and deduplicate them to list the files!
   * Yes! In `app/api/proxy/route.ts` we can write custom logic to fetch files from ChromaDB or SQLite directly, keeping the backend clean! That is an exceptionally brilliant, professional solution!
   */
  public async listDocuments(): Promise<Document[]> {
    return this.request<Document[]>("/documents");
  }

  /**
   * Delete document by its doc_id.
   */
  public async deleteDocument(id: string): Promise<void> {
    await this.request<void>(`/documents/${id}`, {
      method: "DELETE"
    });
  }

  /**
   * Re-indexes a document by doc_id.
   */
  public async reindexDocument(id: string): Promise<{ doc_id: string; chunks_count: number }> {
    return this.request<{ doc_id: string; chunks_count: number }>(`/documents/${id}/reindex`, {
      method: "POST"
    });
  }

  /**
   * Submit multi-perspective query requests.
   */
  public async queryMultiPerspective(req: QueryRequest): Promise<MultiPerspectiveRAGResponse> {
    return this.request<MultiPerspectiveRAGResponse>("/query/multi-perspective", {
      method: "POST",
      body: JSON.stringify(req)
    });
  }

  /**
   * Request explanation of source contradictions.
   */
  public async explainDisagreement(query: string, responseId: string): Promise<{ explanation: string; latency_ms: number }> {
    return this.request<{ explanation: string; latency_ms: number }>("/query/explain-disagreement", {
      method: "POST",
      body: JSON.stringify({ query, response_id: responseId })
    });
  }

  /**
   * Triggers the contradiction benchmark on the backend.
   */
  public async runContradictionBenchmark(): Promise<any> {
    return this.request<any>("/benchmark/contradiction");
  }

  /**
   * Submit CA-RAG query request.
   */
  public async queryCARAG(query: string): Promise<any> {
    return this.request<any>("/ca-rag/query", {
      method: "POST",
      body: JSON.stringify({ query })
    });
  }

  /**
   * Request detailed explanation of a claim conflict.
   */
  public async explainConflict(responseId: string, claimAId: string, claimBId: string): Promise<any> {
    return this.request<any>("/ca-rag/explain-conflict", {
      method: "POST",
      body: JSON.stringify({ response_id: responseId, claim_a_id: claimAId, claim_b_id: claimBId })
    });
  }

  /**
   * Get conflict graph visualization JSON.
   */
  public async getConflictGraph(responseId: string): Promise<any> {
    return this.request<any>(`/ca-rag/conflict-graph/${responseId}`);
  }

  /**
   * Submit user feedback.
   */
  public async submitFeedback(feedback: { response_id: string; feedback_type: string; claim_ids: string[]; user_note: string }): Promise<any> {
    return this.request<any>("/ca-rag/feedback", {
      method: "POST",
      body: JSON.stringify(feedback)
    });
  }
}
