"use client";
import React from "react";
import { IngestionProgress as ProgressItem } from "@/lib/types";
import { 
  FileText, 
  Loader2, 
  CheckCircle2, 
  XCircle, 
  AlertCircle 
} from "lucide-react";
import clsx from "clsx";

interface IngestionProgressProps {
  progressItem: ProgressItem;
  onClear?: () => void;
}

export default function IngestionProgress({ progressItem, onClear }: IngestionProgressProps) {
  const { file_name, status, progress, error, chunks_count } = progressItem;

  // Determine stage text
  let stageText = "Uploading file...";
  let statusColor = "text-accent";
  let showLoader = true;
  let showSuccess = false;
  let showError = false;

  if (status === "chunking") {
    stageText = "Semantic chunking (applying overlap)...";
  } else if (status === "embedding") {
    stageText = "Embedding vectors (SentenceTransformers)...";
  } else if (status === "success") {
    stageText = `Completed successfully. Created ${chunks_count || 0} chunks.`;
    statusColor = "text-success";
    showLoader = false;
    showSuccess = true;
  } else if (status === "error") {
    stageText = error || "Failed to complete ingestion.";
    statusColor = "text-danger";
    showLoader = false;
    showError = true;
  }

  // Parse type of file icon
  const extension = file_name.split(".").pop()?.toLowerCase();
  const isPdf = extension === "pdf";
  const isMd = extension === "md" || extension === "markdown";

  return (
    <div
      className={clsx(
        "rounded-md border p-3.5 shadow-sm transition-all duration-base",
        showError 
          ? "border-danger/30 bg-danger/5" 
          : showSuccess 
            ? "border-success/30 bg-success/5" 
            : "border-border bg-white"
      )}
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 overflow-hidden">
          <FileText 
            size={16} 
            className={clsx(
              isPdf ? "text-danger" : isMd ? "text-accent" : "text-secondary"
            )} 
          />
          <span className="font-sans text-xs font-bold text-primary truncate" title={file_name}>
            {file_name}
          </span>
        </div>
        
        {/* Right side status indicators */}
        <div className="flex items-center gap-2 shrink-0">
          {showLoader && <Loader2 size={13} className="animate-spin text-muted" />}
          {showSuccess && <CheckCircle2 size={14} className="text-success" />}
          {showError && (
            <button
              onClick={onClear}
              className="text-danger hover:text-danger/80 transition-colors"
              title="Clear entry"
            >
              <AlertCircle size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Progress slider bar */}
      {!showError && !showSuccess && (
        <div className="w-full h-1 bg-surface-2 rounded-full overflow-hidden mb-2">
          <div 
            className="h-full bg-accent rounded-full transition-all duration-fast" 
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Stage log and meta */}
      <div className="flex items-center justify-between text-[10px] select-none">
        <span className={clsx("font-sans font-medium truncate flex-1 pr-4", statusColor)}>
          {stageText}
        </span>
        {!showError && !showSuccess && (
          <span className="font-mono text-muted shrink-0 font-semibold">
            {progress}%
          </span>
        )}
      </div>
    </div>
  );
}
