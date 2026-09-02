# Frontend — Can I Park Here?

React + Vite + TypeScript. Structured-selector UI for the Chicago parking
assistant. Talks to the FastAPI backend (`../backend`).

```bash
npm install
cp .env.example .env          # VITE_API_URL -> your backend
npm run dev                   # http://localhost:5173
npm run build                 # -> dist/  (deploy to Vercel Hobby)
```

The user picks **neighborhood → street → block → side → interval → permit**;
that resolves to a canonical `location_id`. `POST /api/parking/analyze` runs the
deterministic rule engine and then the Claude agent, returning the verdict, the
agent's explanation, and a tool-call trace (see the "Agent run inspector").
