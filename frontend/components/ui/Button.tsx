import React from "react";
import clsx from "clsx";
import { Loader2 } from "lucide-react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "outline";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
}

export default function Button({
  children,
  className,
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || isLoading}
      className={clsx(
        "inline-flex items-center justify-center font-sans font-semibold rounded transition-all duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed select-none",
        {
          // Variants
          "bg-accent text-white hover:bg-accent-hover focus-visible:ring-accent": variant === "primary",
          "bg-surface-2 text-primary hover:bg-border focus-visible:ring-border-strong border border-border": variant === "secondary",
          "bg-danger text-white hover:bg-danger/90 focus-visible:ring-danger": variant === "danger",
          "bg-transparent border border-border hover:bg-surface text-secondary hover:text-primary focus-visible:ring-accent": variant === "outline",
          // Sizes
          "px-2.5 py-1 text-xs": size === "sm",
          "px-4 py-2 text-sm": size === "md",
          "px-6 py-3 text-base": size === "lg",
        },
        className
      )}
      {...props}
    >
      {isLoading && <Loader2 size={14} className="mr-2 animate-spin shrink-0" />}
      {children}
    </button>
  );
}
