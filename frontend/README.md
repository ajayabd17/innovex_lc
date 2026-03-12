# Innovex CO-DE-GEN Frontend

Next.js App Router frontend for Innovex Company Detail Generator.

## Setup

1. Install dependencies:
   npm install
2. Configure API base URL:
   frontend/.env.local
3. Run dev server:
   npm run dev

Default API endpoint:
- http://localhost:8000

## Pages

- `/` Submit company and start runs
- `/runs/[runId]` Run status with polling and retry
- `/runs/[runId]/result` Result viewer, copy/download JSON
- `/system/health` Backend health and latency

## Notes

- Polling interval is controlled by `NEXT_PUBLIC_POLL_INTERVAL_MS`.
- Run history is persisted to `sessionStorage`.
