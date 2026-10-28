export function LogoMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <rect width="32" height="32" rx="9" fill="#111511" stroke="#2a342a" />
      <rect x="8" y="17" width="4" height="7" rx="1.5" fill="#c6ff5e" opacity="0.45" />
      <rect x="14" y="12" width="4" height="12" rx="1.5" fill="#c6ff5e" opacity="0.7" />
      <rect x="20" y="7" width="4" height="17" rx="1.5" fill="#c6ff5e" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark className="h-7 w-7" />
      <span className="text-[1.05rem] font-semibold tracking-tight text-fg">Spendly</span>
    </span>
  );
}
