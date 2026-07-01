"use client";

import React, { Component, type ErrorInfo } from "react";
import EmptyState from "./EmptyState";
import type { ErrorBoundaryProps, ErrorBoundaryState } from "@/lib/types";

/**
 * Standard React Class Error Boundary wrapping critical components/sections.
 * Displays a recovery banner using the EmptyState component on runtime errors.
 */
export default class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // Update state to render fallback UI on next pass
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log exception context to browser console/monitoring
    console.error("[ErrorBoundary caught exception]:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="w-full h-full min-h-[300px] flex items-center justify-center p-6 border border-border bg-white rounded-lg select-none">
          <EmptyState
            variant="error"
            title="Component Error Caught"
            description={
              this.state.error?.message ||
              "An exception occurred inside this layout section. Please reload or try again."
            }
            action={{
              label: "Reset Section",
              onClick: this.handleReset,
            }}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
