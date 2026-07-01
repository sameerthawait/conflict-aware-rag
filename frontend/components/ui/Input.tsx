import React from "react";
import clsx from "clsx";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export default React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, type = "text", label, error, ...props },
  ref
) {
  return (
    <div className="flex flex-col gap-1 w-full font-sans">
      {label && (
        <label className="text-xs font-bold text-secondary uppercase tracking-wide select-none">
          {label}
        </label>
      )}
      <input
        type={type}
        ref={ref}
        className={clsx(
          "w-full px-3 py-2 text-sm text-primary bg-white border rounded transition-all duration-fast placeholder-muted focus:outline-none focus:ring-1",
          error
            ? "border-danger focus:border-danger focus:ring-danger"
            : "border-border focus:border-accent focus:ring-accent",
          className
        )}
        {...props}
      />
      {error && <span className="text-[11px] text-danger select-none">{error}</span>}
    </div>
  );
});
