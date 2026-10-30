# ControlIQ — Frontend

Next.js 15 (App Router) client for ControlIQ. See the [root README](../README.md) for full setup and
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for how the frontend fits in.

```bash
npm install
cp .env.example .env.local   # CONTROLIQ_API_URL=http://localhost:8000
npm run dev                  # http://localhost:3000 (requires the FastAPI backend)
npm test                     # Vitest unit tests
npm run lint && npx tsc --noEmit
npm run build && npm run start
```

All `/api/*` requests are proxied to `CONTROLIQ_API_URL` (see `next.config.ts`). Permission checks in
the UI only hide actions; the backend enforces them.
