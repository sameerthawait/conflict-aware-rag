"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle, AlertTriangle, AlertCircle, Info, X } from "lucide-react";
import clsx from "clsx";
import { useToastStore, useToast } from "@/lib/hooks/useToast";
import type { ToastInfo } from "@/lib/types";

/**
 * Individual toast item component handling its own lifecycle, auto-dismiss,
 * and hardware-accelerated CSS progress bars.
 */
function ToastItem({ toast }: { toast: ToastInfo }) {
  const { dismiss } = useToast();
  const [progress, setProgress] = useState(100);
  const [exiting, setExiting] = useState(false);

  const duration = toast.duration ?? 4000;

  // Auto-dismiss logic
  useEffect(() => {
    // Start progress transition
    const progressFrame = requestAnimationFrame(() => {
      setProgress(0);
    });

    const dismissTimer = setTimeout(() => {
      setExiting(true);
      setTimeout(() => {
        dismiss(toast.id);
      }, 150); // Match exit animation speed (150ms)
    }, duration);

    return () => {
      cancelAnimationFrame(progressFrame);
      clearTimeout(dismissTimer);
    };
  }, [toast.id, duration, dismiss]);

  const handleManualDismiss = () => {
    setExiting(true);
    setTimeout(() => {
      dismiss(toast.id);
    }, 150);
  };

  // Icon mapping
  const getIcon = () => {
    switch (toast.type) {
      case "success":
        return <CheckCircle size={16} className="shrink-0 text-success" />;
      case "error":
        return <AlertCircle size={16} className="shrink-0 text-danger" />;
      case "warning":
        return <AlertTriangle size={16} className="shrink-0 text-warning" />;
      case "info":
        return <Info size={16} className="shrink-0 text-accent" />;
      default:
        return <Info size={16} className="shrink-0 text-accent" />;
    }
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className={clsx(
        "relative flex w-full max-w-[360px] flex-col rounded-lg border border-border bg-white shadow-lg pointer-events-auto select-none overflow-hidden transition-all duration-200 transform",
        exiting 
          ? "translate-x-full opacity-0 duration-150" 
          : "translate-x-0 opacity-100 duration-200 animate-slide-up"
      )}
    >
      <div className="flex items-start gap-3 p-4">
        {/* Type Icon */}
        <div className="mt-0.5">{getIcon()}</div>

        {/* Text Details */}
        <div className="flex-1 space-y-1 pr-4">
          <h5 className="font-sans text-xs font-bold text-primary leading-none select-text">
            {toast.title}
          </h5>
          {toast.description && (
            <p className="font-sans text-[11px] text-secondary leading-relaxed select-text">
              {toast.description}
            </p>
          )}

          {/* Action button if provided */}
          {toast.action && (
            <button
              onClick={() => {
                toast.action?.onClick();
                handleManualDismiss();
              }}
              className="mt-2 text-[10px] font-bold text-accent uppercase tracking-wide hover:underline cursor-pointer"
            >
              {toast.action.label}
            </button>
          )}
        </div>

        {/* Close Button */}
        <button
          onClick={handleManualDismiss}
          aria-label="Dismiss notification"
          className="text-muted hover:text-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded p-0.5"
        >
          <X size={14} />
        </button>
      </div>

      {/* Hardware-accelerated progress timer bar */}
      <div className="h-[2px] w-full bg-surface-2 absolute bottom-0 left-0 right-0">
        <div
          className={clsx(
            "h-full transition-all ease-linear",
            toast.type === "success" && "bg-success",
            toast.type === "error" && "bg-danger",
            toast.type === "warning" && "bg-warning",
            toast.type === "info" && "bg-accent"
          )}
          style={{
            width: `${progress}%`,
            transitionDuration: `${duration}ms`,
          }}
        />
      </div>
    </div>
  );
}

/**
 * Root portal wrapper displaying the active stack of toasts in the bottom-right viewport.
 */
export default function ToastContainer() {
  const toasts = useToastStore((state) => state.toasts);

  if (toasts.length === 0) return null;

  return (
    <div 
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2.5 w-full max-w-[360px] pointer-events-none select-none"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
