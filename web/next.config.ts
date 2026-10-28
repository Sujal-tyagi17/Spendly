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
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
