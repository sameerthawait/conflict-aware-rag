"use client";
import React, { useState } from "react";
import { Document } from "@/lib/types";
import DocumentCard from "./DocumentCard";
import { Search, ArrowUpDown, Trash2, ShieldAlert } from "lucide-react";
import clsx from "clsx";

interface DocumentListProps {
  documents: Document[];
  isLoading: boolean;
  onDelete: (id: string) => Promise<void>;
}

type SortField = "file_name" | "file_type" | "chunks_count" | "indexed_at" | "file_size_bytes";

export default function DocumentList({ documents, isLoading, onDelete }: DocumentListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [sortField, setSortField] = useState<SortField>("indexed_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Filter logic
  const filteredDocs = documents.filter((doc) =>
    doc.file_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Sort logic
  const sortedDocs = [...filteredDocs].sort((a, b) => {
    let valA = a[sortField];
    let valB = b[sortField];

    if (typeof valA === "string") {
      return sortOrder === "asc"
        ? (valA as string).localeCompare(valB as string)
        : (valB as string).localeCompare(valA as string);
    }
    
    // Numbers
    return sortOrder === "asc"
      ? (valA as number) - (valB as number)
      : (valB as number) - (valA as number);
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  // Bulk Selection Handlers
  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedIds(new Set(sortedDocs.map((doc) => doc.doc_id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleToggleSelect = (id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    const confirmDelete = window.confirm(
      `Are you sure you want to delete the ${selectedIds.size} selected documents?`
    );
    if (!confirmDelete) return;

    for (const id of Array.from(selectedIds)) {
      try {
        await onDelete(id);
      } catch (err) {
        console.error(`Failed to delete document ${id}:`, err);
      }
    }
    setSelectedIds(new Set());
  };

  const isAllSelected = sortedDocs.length > 0 && selectedIds.size === sortedDocs.length;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-48 border border-border bg-surface rounded-lg select-none">
        <span className="font-sans text-xs text-secondary animate-pulse font-medium">
          Loading document repository database...
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Search & Actions Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Search Query Input */}
        <div className="relative flex-1 max-w-sm">
          <input
            type="text"
            placeholder="Filter documents by name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-border bg-surface-2 rounded-md font-sans text-xs text-primary placeholder-muted focus:outline-none focus:border-border-strong focus:bg-white transition-all duration-fast"
          />
          <Search size={14} className="absolute left-3 top-3 text-muted" />
        </div>

        {/* Bulk Actions (Deletes) */}
        {selectedIds.size > 0 && (
          <button
            onClick={handleBulkDelete}
            className="flex items-center gap-1.5 rounded border border-danger/30 bg-danger/5 hover:bg-danger/10 px-3 py-1.5 font-sans text-xs font-semibold text-danger transition-colors duration-fast"
          >
            <Trash2 size={13} />
            <span>Delete Selected ({selectedIds.size})</span>
          </button>
        )}
      </div>

      {/* Main Documents Table Grid */}
      {sortedDocs.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 border border-dashed border-border bg-surface rounded-lg text-center select-none">
          <ShieldAlert size={28} className="text-muted mb-1.5" />
          <span className="font-sans text-xs font-semibold text-secondary">No Documents Found</span>
          <p className="font-sans text-[11px] text-muted max-w-[240px] mt-0.5">
            {searchQuery ? "No assets matching search criteria." : "Repository is currently empty. Drop files above to index."}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-border border-collapse text-left">
            <thead className="bg-surface select-none font-sans text-xs font-bold text-secondary">
              <tr>
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={isAllSelected}
                    onChange={handleSelectAll}
                    className="rounded border-border text-accent focus:ring-accent"
                  />
                </th>
                <th className="px-4 py-3 cursor-pointer hover:bg-surface-2" onClick={() => handleSort("file_name")}>
                  <div className="flex items-center gap-1">
                    <span>Name</span>
                    <ArrowUpDown size={12} className="text-muted" />
                  </div>
                </th>
                <th className="px-4 py-3 cursor-pointer hover:bg-surface-2 w-20" onClick={() => handleSort("file_type")}>
                  <div className="flex items-center gap-1">
                    <span>Type</span>
                    <ArrowUpDown size={12} className="text-muted" />
                  </div>
                </th>
                <th className="px-4 py-3 cursor-pointer hover:bg-surface-2 w-24" onClick={() => handleSort("chunks_count")}>
                  <div className="flex items-center gap-1 justify-end">
                    <span>Chunks</span>
                    <ArrowUpDown size={12} className="text-muted" />
                  </div>
                </th>
                <th className="px-4 py-3 cursor-pointer hover:bg-surface-2 w-28" onClick={() => handleSort("file_size_bytes")}>
                  <div className="flex items-center gap-1 justify-end">
                    <span>Size</span>
                    <ArrowUpDown size={12} className="text-muted" />
                  </div>
                </th>
                <th className="px-4 py-3 cursor-pointer hover:bg-surface-2 w-40" onClick={() => handleSort("indexed_at")}>
                  <div className="flex items-center gap-1">
                    <span>Indexed At</span>
                    <ArrowUpDown size={12} className="text-muted" />
                  </div>
                </th>
                <th className="px-4 py-3 text-right w-20">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-sans text-xs text-primary">
              {sortedDocs.map((doc) => (
                <DocumentCard
                  key={doc.doc_id}
                  doc={doc}
                  isSelected={selectedIds.has(doc.doc_id)}
                  onSelectToggle={(checked) => handleToggleSelect(doc.doc_id, checked)}
                  onDelete={() => onDelete(doc.doc_id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
