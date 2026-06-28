import React from "react";

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="sticky top-0 z-20 backdrop-blur-xl bg-background/70 border-b border-border px-8 py-5 flex items-end justify-between">
      <div>
        <h1 className="font-heading font-black text-3xl tracking-tight leading-none">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-3">{children}</div>
    </div>
  );
}

export function StatCard({ label, value, sub, className = "", testId }) {
  return (
    <div className={`bg-card border border-border rounded-md p-4 transition-all duration-200 hover:border-white/20 ${className}`} data-testid={testId}>
      <div className="text-xs font-bold uppercase tracking-[0.15em] text-muted-foreground">{label}</div>
      <div className={`text-2xl font-mono font-bold mt-2 ${className.includes("text-") ? "" : ""}`}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}
