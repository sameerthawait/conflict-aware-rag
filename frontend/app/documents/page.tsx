"use client";
import React, { useState } from "react";
import Layout from "@/components/layout/Layout";
import DropZone from "@/components/documents/DropZone";
import DocumentList from "@/components/documents/DocumentList";
import IngestionProgress from "@/components/documents/IngestionProgress";
import { useDocuments } from "@/lib/hooks/useDocuments";
import { IngestionProgress as ProgressItem } from "@/lib/types";
import { FileText, Database } from "lucide-react";

export default function DocumentsPage() {
  const { documents, isDocumentsLoading, uploadFile, deleteDocument } = useDocuments();
  const [ingestionQueue, setIngestionQueue] = useState<ProgressItem[]>([]);

  // File Upload Queue Handler
  const handleUploadFiles = async (files: File[]) => {
    // Process files sequentially to avoid saturating backend thread pools
    for (const file of files) {
      const fileId = `${file.name}-${Date.now()}`;
      
      const newQueueItem: ProgressItem = {
        id: fileId,
        file_name: file.name,
        status: "uploading",
        progress: 0
      };

      setIngestionQueue((prev) => [...prev, newQueueItem]);

      try {
        await uploadFile({
          file,
          onProgress: (pct) => {
            setIngestionQueue((prev) =>
              prev.map((item) =>
                item.id === fileId ? { ...item, progress: pct, status: pct === 100 ? "embedding" : "uploading" } : item
              )
            );
          }
        });

        // Set Success
        setIngestionQueue((prev) =>
          prev.map((item) =>
            item.id === fileId ? { ...item, status: "success", progress: 100 } : item
          )
        );

        // Auto remove success items after 3s
        setTimeout(() => {
          setIngestionQueue((prev) => prev.filter((item) => item.id !== fileId));
        }, 3000);

      } catch (err) {
        // Set Error
        setIngestionQueue((prev) =>
          prev.map((item) =>
            item.id === fileId
              ? {
                  ...item,
                  status: "error",
                  error: err instanceof Error ? err.message : "Ingestion failed."
                }
              : item
          )
        );
      }
    }
  };

  return (
    <Layout title="Document Ingestion Manager">
      <div className="max-w-6xl mx-auto space-y-8 select-none">
        
        {/* Top summary row */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4 select-none">
          <div>
            <span className="font-sans text-xs text-muted block">ACTIVE CORPUS SIZE:</span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Database size={16} className="text-accent" />
              <span className="font-sans text-base font-bold text-primary">
                {isDocumentsLoading ? "Checking..." : `${documents.length} Indexed Files`}
              </span>
            </div>
          </div>
        </div>

        {/* 1. Drag and Drop Upload Hub */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1">
            <h2 className="font-sans text-sm font-bold text-primary mb-1.5">Upload Knowledge Assets</h2>
            <p className="font-sans text-xs text-secondary leading-relaxed mb-4">
              Add Markdown, PDFs, DOCX, or text files. Chunks will be embedded and BM25 search indices will be updated in the background.
            </p>
            <DropZone onUpload={handleUploadFiles} />
          </div>

          {/* 2. Ingestion Progress logs */}
          <div className="md:col-span-2 space-y-4">
            <h2 className="font-sans text-sm font-bold text-primary mb-1.5">Active Ingestions Pipeline</h2>
            {ingestionQueue.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-[140px] border border-dashed border-border bg-surface rounded-lg text-center">
                <FileText size={24} className="text-muted mb-1" />
                <span className="font-sans text-[11px] text-muted">No files currently in pipeline.</span>
              </div>
            ) : (
              <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                {ingestionQueue.map((item) => (
                  <IngestionProgress 
                    key={item.id} 
                    progressItem={item} 
                    onClear={() => setIngestionQueue((prev) => prev.filter((i) => i.id !== item.id))} 
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 3. Document list explorer table */}
        <div className="pt-4">
          <h2 className="font-sans text-sm font-bold text-primary mb-3">Indexed File Repository</h2>
          <DocumentList 
            documents={documents} 
            isLoading={isDocumentsLoading} 
            onDelete={deleteDocument} 
          />
        </div>
      </div>
    </Layout>
  );
}
