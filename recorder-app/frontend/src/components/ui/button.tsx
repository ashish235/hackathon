import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost" | "destructive";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", ...props }, ref) => {
    const base =
      "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50";
    const variants = {
      default:
        "bg-slate-900 text-slate-50 hover:bg-slate-800 focus-visible:ring-slate-400",
      outline:
        "border border-slate-200 bg-transparent hover:bg-slate-100 focus-visible:ring-slate-400",
      ghost: "hover:bg-slate-100 focus-visible:ring-slate-400",
      destructive:
        "bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-500",
    };
    return (
      <button
        ref={ref}
        className={cn(base, variants[variant], className)}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };
