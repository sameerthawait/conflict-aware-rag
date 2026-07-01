import React from "react";
import clsx from "clsx";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "danger" | "info";
}

export default function Badge({
  children,
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded font-sans text-[10px] font-bold uppercase select-none tracking-wider border",
        {
          "bg-surface-2 text-secondary border-border": variant === "default",
          "bg-success/5 text-success border-success/20": variant === "success",
          "bg-warning/5 text-warning border-warning/20": variant === "warning",
          "bg-danger/5 text-danger border-danger/20": variant === "danger",
          "bg-citation text-accent border-citation-border": variant === "info"
        },
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
