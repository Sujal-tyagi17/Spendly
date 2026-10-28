/**
 * Site-wide configuration.
 *
 * NEXT_PUBLIC_APP_URL — where "Explore Spendly" sends people. Defaults to the
 * built-in app at /app. It may also be an absolute URL (for example the legacy
 * Streamlit app). It is inlined into the browser bundle at build time, so it
 * must only ever hold a public URL, never a secret.
 */
const FALLBACK_APP_URL = "/app";

function normalizeUrl(value: string | undefined, fallback = FALLBACK_APP_URL): string {
  const trimmed = value?.trim();
  if (!trimmed) return fallback;
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) return trimmed;
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "http:" && url.protocol !== "https:") return fallback;
    return url.toString().replace(/\/$/, "");
  } catch {
    return fallback;
  }
}

export const site = {
  name: "Spendly",
  tagline: "Every rupee tells a story.",
  description:
    "Turn your bank and UPI statements into a clearer picture of your spending. Discover patterns, understand your habits, and make every rupee count.",
  appUrl: normalizeUrl(process.env.NEXT_PUBLIC_APP_URL),
  siteUrl: normalizeUrl(process.env.NEXT_PUBLIC_SITE_URL, "http://localhost:3000"),
  githubUrl: "https://github.com/Sujal-tyagi17/Spendly",
} as const;

export const isExternalAppUrl = /^https?:\/\//.test(site.appUrl);

export const navLinks = [
  { href: "#product", label: "Product" },
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#privacy", label: "Privacy" },
] as const;
