"use client";

import { create } from "zustand";
import type { ToastInfo } from "@/lib/types";

interface ToastStore {
  toasts: ToastInfo[];
  addToast: (toast: Omit<ToastInfo, "id">) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9);
    set((state) => {
      // Stacking constraint: limit to 3 max. Dismiss oldest.
      const updated = [...state.toasts, { ...toast, id }];
      if (updated.length > 3) {
        updated.shift();
      }
      return { toasts: updated };
    });
  },
  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
}));

/**
 * Global reactive hook to dispatch and manage toast alerts.
 */
export const useToast = () => {
  const addToast = useToastStore((state) => state.addToast);
  const removeToast = useToastStore((state) => state.removeToast);

  const toast = {
    success: (title: string, description?: string, duration = 4000) =>
      addToast({ type: "success", title, description, duration }),
    error: (title: string, description?: string, duration = 8000) =>
      addToast({ type: "error", title, description, duration }),
    warning: (title: string, description?: string, duration = 4000) =>
      addToast({ type: "warning", title, description, duration }),
    info: (title: string, description?: string, duration = 4000) =>
      addToast({ type: "info", title, description, duration }),
  };

  return {
    toasts: useToastStore((state) => state.toasts),
    toast,
    dismiss: removeToast,
  };
};
