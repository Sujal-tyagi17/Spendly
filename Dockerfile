# One container for a free Render web service: the Next.js dashboard (public, on $PORT)
# and the FastAPI backend (private, on 127.0.0.1:8000). The browser only ever talks to
# Next.js, which forwards /api/* to the API (see web/next.config.ts).

# ---- 1. Build the dashboard ------------------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG NEXT_PUBLIC_SITE_URL=https://spendly-insights.onrender.com
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    SPENDLY_API_URL=http://127.0.0.1:8000 \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

# ---- 2. Runtime: Python for the API, plus the Node binary for Next.js -------------------
FROM python:3.12-slim-bookworm
COPY --from=web /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY api/ api/
COPY src/ src/
COPY sql/ sql/
COPY config/ config/
COPY assets/ assets/
COPY data/sample_transactions.csv data/
COPY docs/anomaly_evaluation.json docs/
COPY scripts/start-render.sh scripts/
COPY --from=web /web/.next web/.next
COPY --from=web /web/node_modules web/node_modules
COPY --from=web /web/public web/public
COPY --from=web /web/package.json web/next.config.ts web/

# Public mode: every visitor gets private, in-memory data for their session only.
ENV SPENDLY_PUBLIC_DEPLOYMENT=true \
    SPENDLY_API_URL=http://127.0.0.1:8000 \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PORT=10000

RUN useradd --create-home spendly && chown -R spendly /app/data
USER spendly
EXPOSE 10000
CMD ["sh", "scripts/start-render.sh"]
