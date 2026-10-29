import type { NextConfig } from "next";

/**
 * The browser always calls same-origin `/api/*`; Next.js forwards those requests
 * to the FastAPI backend. SPENDLY_API_URL is read on the server only (no
 * NEXT_PUBLIC_ prefix), so the backend address is never baked into client code.
 */
const apiUrl = (process.env.SPENDLY_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

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
    // Baseline hardening for every page. A strict Content-Security-Policy is left to the
    // deployer because it depends on the host (see README "Security").
    return [{
      source: "/:path*",
      headers: [
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
