Local-only Next.js app. No separate backend service required.

## Getting Started

1) Configure env

- Copy `.env.example` → `.env.local`
- Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- Set `TWELVEDATA_API_KEY` (used by `app/api/*` routes for `time_series`)

2) Install + run

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Notes

- Market candles are fetched from TwelveData `time_series` (10 daily candles).
- If `TWELVEDATA_API_KEY` is missing, the app falls back to deterministic demo candles so the UI remains usable locally.

## Commands

- `npm run dev`
- `npm run build`
- `npm run lint`
