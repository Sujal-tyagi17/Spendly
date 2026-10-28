# Spendly — marketing website

The public landing page for Spendly. It's a separate Next.js app that lives next to the Streamlit
analytics app. **It doesn't change or replace the Python code**: its job is to present the product
and link people to the running Streamlit app.

```
Spendly/
├── app.py, src/, sql/, tests/ …   ← Streamlit analytics app (Python)
└── web/                           ← this marketing site (Next.js)
```

## Stack

- Next.js 16 (App Router, Turbopack), React 19, TypeScript
- Tailwind CSS v4: design tokens live in `app/globals.css` (`@theme`)
- Motion (`motion/react`) for animation. `MotionConfig reducedMotion="user"` makes it respect the
  visitor's reduced-motion setting.
- Lucide icons. Geist fonts are self-hosted through the `geist` package, so the build never contacts
  Google Fonts.
- Charts are hand-built SVG. No chart library is needed for illustrative previews.

## Structure

```
web/
├── app/
│   ├── layout.tsx            # fonts, metadata, Open Graph, skip link, Motion provider
│   ├── page.tsx              # composes the sections
│   ├── globals.css           # tokens, grain, atmosphere, reduced-motion rules
│   ├── icon.svg              # favicon
│   └── opengraph-image.png   # social preview (+ twitter-image.png)
├── components/
│   ├── nav.tsx               # transparent → solid on scroll, mobile menu
│   ├── hero.tsx, hero-dashboard.tsx
│   ├── product-preview.tsx   # larger dashboard preview
│   ├── before-after.tsx      # interactive raw-statement vs Spendly toggle
│   ├── features.tsx          # four feature cards with mini visuals
│   ├── how-it-works.tsx, sql-section.tsx, privacy.tsx, final-cta.tsx, footer.tsx
│   └── charts.tsx, count-up.tsx, reveal.tsx, cta.tsx, logo.tsx, section-heading.tsx
└── lib/
    ├── site.ts               # app URL (env), GitHub URL, nav links
    └── demo-data.ts          # synthetic numbers from Spendly's demo dataset
```

## Run locally

You need Node.js 20.9 or newer.

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

To make "Explore Spendly" open your local Streamlit app, start it in another terminal from the repo root:

```bash
streamlit run app.py # http://localhost:8501 (the site's default target)
```

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
| `NEXT_PUBLIC_APP_URL` | URL of the running Streamlit app; every "Explore Spendly" button links here | `http://localhost:8501` |
| `NEXT_PUBLIC_SITE_URL` | Public URL of this site, used to build absolute Open Graph image URLs | `http://localhost:3000` |

Copy `.env.example` to `.env.local` to change them locally. `NEXT_PUBLIC_` values are **inlined at
build time** and visible in the browser, so they must only ever hold public URLs, never secrets.
Invalid values fall back to the defaults.

## Deploy

1. **Deploy the Streamlit app first** (see the root README → Deployment) and copy its URL, e.g.
   `https://your-app.streamlit.app`.
2. **Deploy this site on Vercel:**
   - Import the GitHub repo and set **Root Directory** to `web`. The framework is detected as Next.js.
   - Add the environment variables `NEXT_PUBLIC_APP_URL=https://your-app.streamlit.app` and
     `NEXT_PUBLIC_SITE_URL=https://your-site.vercel.app`.
   - Deploy. If you change a variable later, redeploy, because the values are inlined at build time.

Any host that runs `next build` / `next start` works the same way.

## Content rules

- Every dashboard preview uses **synthetic** numbers taken from Spendly's built-in demo dataset and is
  labelled "Illustrative · synthetic data".
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
