# Frontend

Responsive React + TypeScript support workspace built with Vite, Tailwind CSS, and shadcn-style UI primitives.

## Run the preview

```bash
npm install
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). The default page is the demo profile selector for Alex and Taylor. Choose either profile to explore the customer support experience.

The frontend is currently a **local design preview**. Its account, conversation, approval, feedback, and article examples are fictional and held in browser memory only. The interface labels preview answers and local state; no action is sent to or saved by the backend. The optional query `?view=workspace`, `?view=knowledge`, or `?view=account` opens a preview screen directly for design review.

## API integration boundary

`src/api/types.ts` mirrors shared wire types from `../API_CONTRACT.md`, and `src/api/client.ts` contains the credentialed HTTP methods and structured error handling for the contracted endpoints. UI flows currently use typed fixtures from `src/data/demo.ts`; the live client is not connected to those flows yet. In the integration phase, replace the preview state handlers with the API client, restore the session through `/me`, and keep the preview fixtures out of the live request path.

Set `VITE_API_BASE_URL` to configure the backend origin when integration is enabled. No backend or provider secrets belong in frontend environment variables.

## Checks

```bash
npm run build
```
