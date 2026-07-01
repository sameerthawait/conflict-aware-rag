"use client";
import React, { useState } from "react";
import { Document } from "@/lib/types";
import { useDocuments } from "@/lib/hooks/useDocuments";
import { formatBytes, formatDateRelative } from "@/lib/utils/formatters";
import { 
  FileText, 
  Trash2, 
  RefreshCw, 
  FileCode, 
  Loader2, 
  CheckCircle2 
} from "lucide-react";
import clsx from "clsx";

interface DocumentCardProps {
  doc: Document;
  isSelected: boolean;
  onSelectToggle: (checked: boolean) => void;
  onDelete: () => Promise<void>;
}

export default function DocumentCard({ doc, isSelected, onSelectToggle, onDelete }: DocumentCardProps) {
  const { reindexDocument } = useDocuments();
  const [isReindexing, setIsReindexing] = useState(false);
  const [reindexSuccess, setReindexSuccess] = useState(false);

  const { doc_id, file_name, file_type, file_size_bytes, chunks_count, indexed_at } = doc;

  const handleReindex = async () => {
    setIsReindexing(true);
    setReindexSuccess(false);
    try {
      await reindexDocument(doc_id);
      setReindexSuccess(true);
      setTimeout(() => setReindexSuccess(false), 3000);
    } catch (err) {
      alert(`Re-indexing failed: ${err instanceof Error ? err.message : "Server error"}`);
    } finally {
      setIsReindexing(false);
    }
  };

  const handleDelete = async () => {
    const confirm = window.confirm(`Are you sure you want to permanently delete document '${file_name}'?`);
    if (confirm) {
      try {
        await onDelete();
      } catch (err) {
        alert(`Deletion failed: ${err instanceof Error ? err.message : "Server error"}`);
      }
    }
  };

  // Define icon and coloring depending on extension
  const isPdf = file_type.toLowerCase() === "pdf" || file_name.endsWith(".pdf");
  const isMd = file_type.toLowerCase() === "markdown" || file_name.endsWith(".md") || file_name.endsWith(".markdown");

  return (
    <tr className={clsx("hover:bg-surface/50 transition-colors", isSelected && "bg-accent/5")}>
      {/* 1. Selection Checkbox */}
      <td className="px-4 py-3 select-none">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => onSelectToggle(e.target.checked)}
          className="rounded border-border text-accent focus:ring-accent"
        />
      </td>

      {/* 2. File Name & Icon */}
      <td className="px-4 py-3 font-sans font-medium text-primary max-w-sm truncate">
        <div className="flex items-center gap-2 overflow-hidden" title={file_name}>
          {isPdf ? (
            <FileText size={15} className="text-danger shrink-0" />
          ) : isMd ? (
            <FileCode size={15} className="text-accent shrink-0" />
          ) : (
            <FileText size={15} className="text-secondary shrink-0" />
          )}
          <span className="truncate">{file_name}</span>
        </div>
      </td>

      {/* 3. File Type */}
      <td className="px-4 py-3 text-secondary font-mono text-[11px] uppercase">
        {file_type || file_name.split(".").pop() || "unknown"}
      </td>

      {/* 4. Chunk count */}
      <td className="px-4 py-3 text-right font-semibold text-primary">
        <span className="bg-surface-2 px-2 py-0.5 rounded border border-border text-xs">
          {chunks_count}
        </span>
      </td>

      {/* 5. Document Size */}
      <td className="px-4 py-3 text-right font-mono text-secondary">
        {formatBytes(file_size_bytes)}
      </td>

      {/* 6. Ingest Date */}
      <td className="px-4 py-3 text-secondary select-none" title={new Date(indexed_at).toLocaleString()}>
        {formatDateRelative(indexed_at)}
      </td>

      {/* 7. Action Button Panel */}
      <td className="px-4 py-3 text-right select-none">
        <div className="flex items-center justify-end gap-1">
          {/* Re-indexing Action */}
          <button
            onClick={handleReindex}
            disabled={isReindexing}
            className="rounded p-1 text-muted hover:bg-surface-2 hover:text-primary transition-colors disabled:opacity-50"
            title="Re-index document"
          >
            {isReindexing ? (
              <Loader2 size={13} className="animate-spin" />
            ) : reindexSuccess ? (
              <CheckCircle2 size={13} className="text-success" />
            ) : (
              <RefreshCw size={13} />
            )}
          </button>

          {/* Delete Action */}
          <button
            onClick={handleDelete}
            className="rounded p-1 text-muted hover:bg-surface-2 hover:text-danger transition-colors"
            title="Delete document"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </td>
    </tr>
  );
}
