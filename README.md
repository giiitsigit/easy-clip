Easy-clip

Vercel-compatible video clip tool with:
- Static frontend under `public/`
- Node.js serverless API under `api/`

API:
- `POST /api/index`
  - body: `{ "sourceUrl": "...", "timestamps": "00:00:05 00:00:10", "mode": "horizontal|vertical|both" }`

Deploy with Vercel.
