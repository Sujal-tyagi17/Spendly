import { navLinks, site } from "@/lib/site";
import { Logo } from "./logo";

function GitHubIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="currentColor">
      <path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.56-.29-5.25-1.28-5.25-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.04 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.58.23 2.75.11 3.04.74.81 1.19 1.83 1.19 3.09 0 4.41-2.7 5.38-5.27 5.67.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-line bg-ink">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <Logo />
          <p className="mt-4 max-w-xs text-[0.9rem] leading-relaxed text-muted">{site.tagline}</p>
          <p className="mt-4 max-w-sm text-[0.78rem] leading-relaxed text-faint">
            Previews on this page use synthetic demonstration data. Spendly is a personal analytics tool, not a
            regulated financial service.
          </p>
        </div>
        <nav aria-label="Footer — product">
          <p className="eyebrow mb-4">Product</p>
          <ul className="space-y-2.5 text-[0.9rem]">
            {navLinks.map((l) => (
              <li key={l.href}><a href={l.href} className="text-muted transition-colors hover:text-fg">{l.label}</a></li>
            ))}
            <li>
              <a href={site.appUrl} target="_blank" rel="noopener noreferrer" className="text-muted transition-colors hover:text-fg">
                Open the app<span className="sr-only"> (new tab)</span>
              </a>
            </li>
          </ul>
        </nav>
        <nav aria-label="Footer — resources">
          <p className="eyebrow mb-4">Resources</p>
          <ul className="space-y-2.5 text-[0.9rem]">
            <li>
              <a href={site.githubUrl} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-muted transition-colors hover:text-fg">
                <GitHubIcon className="h-4 w-4" /> Source on GitHub<span className="sr-only"> (new tab)</span>
              </a>
            </li>
            <li>
              <a href={`${site.githubUrl}#20-privacy-and-security`} target="_blank" rel="noopener noreferrer"
                className="text-muted transition-colors hover:text-fg">
                Privacy details<span className="sr-only"> (new tab)</span>
              </a>
            </li>
            <li>
              <a href={`${site.githubUrl}#23-known-limitations`} target="_blank" rel="noopener noreferrer"
                className="text-muted transition-colors hover:text-fg">
                Known limitations<span className="sr-only"> (new tab)</span>
              </a>
            </li>
          </ul>
        </nav>
      </div>
      <div className="border-t border-line/70">
        <p className="mx-auto max-w-7xl px-5 py-6 text-[0.78rem] text-faint sm:px-8">
          © 2026 Spendly · Built by Sujal Tyagi
        </p>
      </div>
    </footer>
  );
}
