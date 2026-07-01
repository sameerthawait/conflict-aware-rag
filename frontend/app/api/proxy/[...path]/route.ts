import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const DOCUMENTS_FILE = path.join(process.cwd(), "..", "data", "documents.json");

// Helper to read local mock document catalog state
async function readDocuments(): Promise<any[]> {
  try {
    const data = await fs.readFile(DOCUMENTS_FILE, "utf-8");
    return JSON.parse(data);
  } catch {
    return [];
  }
}

// Helper to update local mock document catalog state
async function writeDocuments(docs: any[]): Promise<void> {
  await fs.mkdir(path.dirname(DOCUMENTS_FILE), { recursive: true });
  await fs.writeFile(DOCUMENTS_FILE, JSON.stringify(docs, null, 2), "utf-8");
}

/**
 * Standard utility to forward request details to Python FastAPI service.
 */
async function forwardRequest(req: NextRequest, subpath: string) {
  const url = `${BACKEND_URL}/${subpath}`;
  const method = req.method;
  const headers = new Headers();

  // Forward existing request headers to maintain token authorizations (X-API-Key)
  req.headers.forEach((value, key) => {
    const k = key.toLowerCase();
    if (!["host", "connection", "content-length", "content-type", "accept-encoding"].includes(k)) {
      headers.set(key, value);
    }
  });

  const config: RequestInit = {
    method,
    headers,
  };

  // Bind body contents if request contains payloads
  if (["POST", "PUT", "PATCH"].includes(method)) {
    const contentType = req.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const bodyText = await req.text();
      config.body = bodyText;
      headers.set("Content-Type", "application/json");
    } else {
      config.body = req.body;
    }
  }

  try {
    const response = await fetch(url, config);
    
    // Read raw text to handle varying response codes and shapes
    const responseText = await response.text();
    let responseData;
    try {
      responseData = JSON.parse(responseText);
    } catch {
      responseData = responseText;
    }

    return NextResponse.json(responseData, { status: response.status });
  } catch (error: any) {
    console.error(`Proxy forwarding error for path /${subpath}:`, error);
    return NextResponse.json(
      { detail: `API Proxy forwarding failed: ${error.message}` },
      { status: 502 }
    );
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: pathSegments } = await params;
  const fullPath = pathSegments.join("/");

  // Handle client listing document catalog
  if (fullPath === "documents") {
    const docs = await readDocuments();
    return NextResponse.json(docs);
  }

  // Re-route token billing request to corresponding endpoint
  if (fullPath === "admin/costs") {
    return forwardRequest(req, "admin/costs");
  }

  return forwardRequest(req, fullPath);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: pathSegments } = await params;
  const fullPath = pathSegments.join("/");

  // Custom interception for file ingestion
  if (fullPath === "ingest") {
    try {
      const formData = await req.formData();
      const file = formData.get("file") as File;
      if (!file) {
        return NextResponse.json({ detail: "Multipart Form Data upload does not contain a file." }, { status: 400 });
      }

      // Create a temporary local file copy in data/raw (mounted inside container as /app/data/raw)
      const tempDir = path.join(process.cwd(), "..", "data", "raw");
      await fs.mkdir(tempDir, { recursive: true });
      const tempFilePath = path.join(tempDir, file.name);
      const containerFilePath = `/app/data/raw/${file.name}`;

      const buffer = Buffer.from(await file.arrayBuffer());
      await fs.writeFile(tempFilePath, buffer);

      // Invoke backend REST pipeline ingestion passing container path
      const headers = new Headers();
      const apiKey = req.headers.get("x-api-key");
      if (apiKey) {
        headers.set("X-API-Key", apiKey);
      }
      headers.set("Content-Type", "application/json");

      const backendResponse = await fetch(`${BACKEND_URL}/ingest`, {
        method: "POST",
        headers,
        body: JSON.stringify({ file_path: containerFilePath }),
      });

      const responseText = await backendResponse.text();
      let backendData;
      try {
        backendData = JSON.parse(responseText);
      } catch {
        backendData = { message: responseText };
      }

      if (backendResponse.ok && backendData.status === "success") {
        // Catalog successfully ingested file into SQLite index tracker
        const docs = await readDocuments();
        const docId = backendData.doc_id || "doc-" + Math.random().toString(36).substring(7);
        const existingIdx = docs.findIndex((d) => d.doc_id === docId);

        const newDocEntry = {
          doc_id: docId,
          file_name: file.name,
          file_type: file.name.split(".").pop() || "unknown",
          file_size_bytes: file.size,
          chunks_count: backendData.chunks_count || 0,
          indexed_at: new Date().toISOString()
        };

        if (existingIdx !== -1) {
          docs[existingIdx] = newDocEntry;
        } else {
          docs.push(newDocEntry);
        }

        await writeDocuments(docs);
      }

      // Cleanup local temporary buffer
      try {
        await fs.unlink(tempFilePath);
      } catch (e) {
        console.warn("Failed to cleanup ingestion temp file:", e);
      }

      return NextResponse.json(backendData, { status: backendResponse.status });
    } catch (err: any) {
      console.error("Ingestion proxy failed:", err);
      return NextResponse.json({ detail: `Ingestion proxy failed: ${err.message}` }, { status: 500 });
    }
  }

  // Handle reindex simulation
  if (pathSegments[0] === "documents" && pathSegments.length === 3 && pathSegments[2] === "reindex") {
    const docId = pathSegments[1];
    const docs = await readDocuments();
    const docIdx = docs.findIndex((d) => d.doc_id === docId);
    
    if (docIdx === -1) {
      return NextResponse.json({ detail: "Document target ID not found." }, { status: 404 });
    }

    // Refresh simulation timestamp
    docs[docIdx].indexed_at = new Date().toISOString();
    await writeDocuments(docs);

    return NextResponse.json({
      status: "success",
      doc_id: docId,
      chunks_count: docs[docIdx].chunks_count,
      message: "Document index successfully re-built."
    });
  }

  return forwardRequest(req, fullPath);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: pathSegments } = await params;

  // Handle single item deletion from index catalog
  if (pathSegments[0] === "documents" && pathSegments.length === 2) {
    const docId = pathSegments[1];
    const docs = await readDocuments();
    const filtered = docs.filter((d) => d.doc_id !== docId);
    await writeDocuments(filtered);
    return new NextResponse(null, { status: 204 });
  }

  return forwardRequest(req, pathSegments.join("/"));
}
