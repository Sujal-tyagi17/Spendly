/**
 * Site-wide configuration.
 *
 * NEXT_PUBLIC_APP_URL — where the Streamlit analytics app lives. It is inlined
 * into the browser bundle at build time, so it must only ever hold a public URL
 * (never a secret). Locally it falls back to Streamlit's default port.
 */
const FALLBACK_APP_URL = "http://localhost:8501";

function normalizeUrl(value: string | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) return FALLBACK_APP_URL;
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "http:" && url.protocol !== "https:") return FALLBACK_APP_URL;
    return url.toString().replace(/\/$/, "");
  } catch {
    return FALLBACK_APP_URL;
  }
}

export const site = {
  name: "Spendly",
  tagline: "Every rupee tells a story.",
  description:
    "Turn your bank and UPI statements into a clearer picture of your spending. Discover patterns, understand your habits, and make every rupee count.",
  appUrl: normalizeUrl(process.env.NEXT_PUBLIC_APP_URL),
  siteUrl: normalizeUrl(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  githubUrl: "https://github.com/Sujal-tyagi17/Spendly",
} as const;

export const navLinks = [
  { href: "#product", label: "Product" },
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#privacy", label: "Privacy" },
] as const;
