import type { NextConfig } from "next";

/**
 * The browser always calls same-origin `/api/*`; Next.js forwards those requests
 * to the FastAPI backend. SPENDLY_API_URL is read on the server only (no
 * NEXT_PUBLIC_ prefix), so the backend address is never baked into client code.
 */
const apiUrl = (process.env.SPENDLY_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const isDev = process.env.NODE_ENV === "development";

/**
 * Content-Security-Policy built from what the app actually loads: its own scripts, styles,
 * fonts (geist is self-hosted) and images; API calls to the same origin. Nothing third-party.
 * 'unsafe-inline' is needed for scripts because Next.js inlines its hydration data and these
 * pages are statically prerendered (a per-request nonce would force dynamic rendering), and for
 * styles because Motion and Recharts set inline style attributes. Dev mode also needs eval + HMR.
 */
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  poweredByHeader: false,
  async headers() {
    // Baseline hardening for every page. Add Strict-Transport-Security at the HTTPS host (see README "Security").
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy", value: csp },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      ],
    }];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
