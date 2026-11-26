# Frontend

React, TypeScript and Vite support workspace. The live interface uses the API in `src/api/client.ts` and the contracted types in `src/api/types.ts`. It restores the signed session, conversations, feedback and approval cards from the backend; it does not use the preview fixtures for live answers or actions. Profile selection is a fictional demo, not real authentication.

```bash
cp .env.example .env.local  # set VITE_API_BASE_URL if the backend is not localhost:8000
npm ci
npm run dev
npm run build
```

Open `http://localhost:5173` and ensure the backend's `FRONTEND_ORIGIN` matches the browser origin exactly. The frontend sends credentialed requests. Never put provider credentials in frontend configuration. For complete setup, limitations and verification results, see the [root README](../README.md).
