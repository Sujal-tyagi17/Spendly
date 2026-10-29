# Spendly web — landing page + app (Spendly 2.0)

The Next.js front end for Spendly:

- `/` is the marketing landing page.
- `/app/*` is the redesigned app: Overview, Transactions, Spending Insights, Recurring Payments, Data Quality,
  and Import & Settings.

**It doesn't do any financial maths.** Every number comes from the FastAPI layer (`../api`), which reuses the
existing Python modules and SQL files. The browser calls same-origin `/api/*`, and `next.config.ts` forwards
those calls to `SPENDLY_API_URL`.

```
Spendly/
├── src/, sql/      ← Python core (single source of truth for every metric)
├── api/            ← FastAPI layer over src/
├── app.py          ← classic Streamlit UI (still works)
└── web/            ← this Next.js app
```

## Stack

- Next.js 16 (App Router, Turbopack), React 19, TypeScript
- Tailwind CSS v4: design tokens live in `app/globals.css` (`@theme`)
- Motion (`motion/react`) for animation. `MotionConfig reducedMotion="user"` makes it respect the
  visitor's reduced-motion setting.
- Lucide icons. Geist fonts are self-hosted through the `geist` package, so the build never contacts
  Google Fonts.
- Recharts draws the app's charts (trend, weekday, period comparison). Each chart has a "View as table"
  fallback. The landing page uses hand-built SVG.

## Structure

```
web/
├── app/
│   ├── layout.tsx            # fonts, metadata, Open Graph, skip link, Motion provider
│   ├── page.tsx              # composes the sections
│   ├── globals.css           # tokens, grain, atmosphere, reduced-motion rules
│   ├── icon.svg              # favicon
│   └── opengraph-image.png   # social preview (+ twitter-image.png)
├── app/app/                  # the app: layout + one folder per page
│   ├── layout.tsx            # AppProvider + AppShell
│   ├── page.tsx              # Overview
│   └── transactions/ insights/ recurring/ quality/ import/
├── components/
│   ├── app/                  # shell (sidebar, header, mobile drawer), filters, charts, edit dialog
│   ├── ui/                   # design system: Button, Card, MetricCard, InsightCard, badges, states,
│   │                         #   ConfirmDialog, UploadDropzone, MultiSelect, InfoTip, Toaster
│   ├── nav.tsx               # landing page: transparent → solid on scroll, mobile menu
│   ├── hero.tsx, hero-dashboard.tsx
│   ├── product-preview.tsx   # larger dashboard preview
│   ├── before-after.tsx      # interactive raw-statement vs Spendly toggle
│   ├── features.tsx          # four feature cards with mini visuals
│   ├── how-it-works.tsx, sql-section.tsx, privacy.tsx, final-cta.tsx, footer.tsx
│   └── charts.tsx, count-up.tsx, reveal.tsx, cta.tsx, logo.tsx, section-heading.tsx
└── lib/
    ├── api.ts                # fetch client (mode + session headers), useApi hook
    ├── store.tsx             # app state: data mode, global filters, meta, toasts
    ├── hooks.ts, types.ts, format.ts
    ├── site.ts               # app URL (env), GitHub URL, nav links
    └── demo-data.ts          # synthetic numbers for the landing-page previews
```

## Run locally

You need Node.js 20.9 or newer.

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

The app needs the API. Start it in another terminal from the repo root:

```bash
uvicorn api.main:app --reload --port 8000
```

If the API isn't running, the app shows a clear "API isn't reachable" message.

Other commands:

```bash
npm run lint         # ESLint
npx tsc --noEmit     # type check
npm run build        # production build
npm start            # serve the production build
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SPENDLY_API_URL` | Where `/api/*` is forwarded. **Server-side only**, never sent to the browser | `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_APP_URL` | Target of the "Explore Spendly" / "Try the demo" buttons | `/app` |
| `NEXT_PUBLIC_SITE_URL` | Public URL of this site, used for absolute Open Graph image URLs | `http://localhost:3000` |

Copy `.env.example` to `.env.local` to change them. `NEXT_PUBLIC_` values are **inlined at build time**, so
they must only ever hold public URLs. Invalid values fall back to the defaults.

## Deploy

1. Deploy the API first (see the root README → "Spendly 2.0: web app + API"), with
   `SPENDLY_PUBLIC_DEPLOYMENT=true`.
2. On Vercel, import the repo and set **Root Directory** to `web`. Add `SPENDLY_API_URL=https://your-api-host`
   and `NEXT_PUBLIC_SITE_URL=https://your-site`, then deploy.

## App behaviour

- **Global filters** (date range, categories, types, merchants) apply to Overview, Transactions, Insights and
  Recurring, like the original sidebar. They're kept per data mode for the browser session, and switching data
  mode clears them.
- **Data mode** (Demo / My data) lives in the sidebar. Demo data is clearly labelled everywhere, and imports are
  only possible in My data.
- **Import:** choose a PDF, read it, review the preview, then import. Nothing is saved before you confirm.
- **Editing:** single rows, or a whole merchant after a confirmation that shows the exact number of affected rows.
- **Overview** shows executive KPIs from `/api/overview` → `executive` (no maths in React), the "why spending
  changed" story, chart drill-downs (select a month, category or merchant), and a **Monthly report (PDF)** button
  that downloads `/api/report/monthly.pdf` with the current non-date filters.
- **Demo:** the landing page's "Try the demo" links to `/app?mode=demo`, which always opens synthetic data.
- **Data Quality** (`/app/quality`) is a scorecard: six dimensions with numerator and denominator (no combined
  score), findings with severity and links to affected rows, a trend from the second import, and filters by
  import and issue type. The import preview shows the same validation report before you confirm.
- **Unusual payments** (Spending Insights) show method, reference distribution, median, deviation and the
  explanation, with "expected" / "dismiss" reviews and the synthetic evaluation results.
- **Budget Planner** (`/app/budgets`) has its own month picker instead of the global filters. It covers
  create, edit, delete (with confirmation), copying from the previous month, a drivers panel, and an empty
  state. Status is always shown with text and an icon, not colour alone, and both charts have a table view.
  All numbers come from `/api/budgets`.
- **Count-up** animates only on first load. Later filter changes update numbers instantly.

## Content rules

- Landing-page previews use **synthetic** numbers taken from Spendly's built-in demo dataset and are
  labelled "Illustrative · synthetic data". The app itself shows only real API data.
- There are no testimonials, user counts or performance claims.
- Privacy statements match the Python implementation: `src/pdf_parser.py`, `src/privacy.py`,
  `src/database.py`, `src/ai.py` and `tests/test_privacy.py`.
- The SQL shown is a simplified excerpt of the real files in `../sql/`.

## Accessibility & motion

- Semantic landmarks, a skip link, one `h1`, a logical heading order and keyboard-reachable controls.
  The tabs use `role="tab"` and `aria-selected`.
- Reduced motion turns off float, glow, draw and count-up animations. Numbers show their final values
  straight away, and screen readers always hear the final numbers.
- Animations use `transform` and `opacity`, and run once when a section scrolls into view.
  There's no scroll hijacking.
- On small screens the background blur is turned off for performance, and the floating dashboard
  cards stack vertically.
