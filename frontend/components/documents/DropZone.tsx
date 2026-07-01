"use client";
import React, { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { UploadCloud } from "lucide-react";
import clsx from "clsx";

interface DropZoneProps {
  onUpload: (files: File[]) => void;
}

export default function DropZone({ onUpload }: DropZoneProps) {
  const maxMb = parseInt(process.env.NEXT_PUBLIC_MAX_FILE_SIZE_MB || "10", 10);
  const maxBytes = maxMb * 1024 * 1024;

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) {
        onUpload(acceptedFiles);
      }
    },
    [onUpload]
  );

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    maxSize: maxBytes,
    accept: {
      "application/pdf": [".pdf"],
      "text/markdown": [".md", ".markdown"],
      "text/plain": [".txt"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"]
    }
  });

  return (
    <div
      {...getRootProps()}
      className={clsx(
        "flex flex-col items-center justify-center border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all duration-fast focus-visible:outline-none focus-visible:border-accent",
        isDragActive && !isDragReject && "border-accent bg-accent/5",
        isDragReject && "border-danger bg-danger/5",
        !isDragActive && "border-border bg-surface-2 hover:border-border-strong hover:bg-surface"
      )}
    >
      <input {...getInputProps()} />
      <UploadCloud
        size={32}
        className={clsx(
          "mb-2.5 transition-colors duration-fast",
          isDragActive && !isDragReject ? "text-accent" : isDragReject ? "text-danger" : "text-muted"
        )}
      />
      <span className="font-sans text-xs font-bold text-primary block">
        {isDragActive ? "Drop assets to index" : "Drop files here"}
      </span>
      <span className="font-sans text-[11px] text-accent font-semibold block mt-1 hover:text-accent-hover underline">
        or click to select files
      </span>
      <span className="font-sans text-[10px] text-muted block mt-3 select-none">
        Supports: PDF, MD, TXT, DOCX (Max {maxMb}MB)
      </span>
    </div>
  );
}
