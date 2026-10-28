import { AlertOctagon, RefreshCw } from "lucide-react";
import { Button } from "./button";

export function EmptyState({ icon: Icon, title, children, action }: {
  icon?: React.ComponentType<{ className?: string }>; title: string; children?: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line-2 bg-ink-2/50 px-6 py-12 text-center">
      {Icon ? (
        <span className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-card text-lime-2">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
      ) : null}
      <p className="text-[1rem] font-semibold text-fg">{title}</p>
      {children ? <div className="mt-2 max-w-md text-[0.88rem] leading-relaxed text-muted">{children}</div> : null}
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-white/[0.05] ${className}`} aria-hidden="true" />;
}

export function LoadingState({ label = "Loading…", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-2xl border border-err/30 bg-err/5 p-5 sm:flex-row sm:items-center">
      <AlertOctagon className="h-5 w-5 shrink-0 text-[#ff9b8f]" aria-hidden="true" />
      <p className="flex-1 text-[0.88rem] text-fg/90">{message}</p>
      {onRetry ? (
        <Button size="sm" onClick={onRetry}><RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />Try again</Button>
      ) : null}
    </div>
  );
}
