# SchemeFinder React Frontend

Modern user-facing frontend for the Government Scheme Recommendation Agent.

This app does not use mock scheme data or a local scheme dataset. It calls the existing FastAPI backend:

- `POST /recommend`
- `GET /health`

## Local setup

```bash
npm install
copy .env.example .env
npm run dev
```

Set the backend URL in `.env`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Open the Vite URL shown in the terminal, usually `http://127.0.0.1:5173`.

## Production

Set `VITE_API_URL` to your deployed FastAPI backend URL in your hosting provider, then run:

```bash
npm run build
```

The static production app is generated in `dist/`.

## Vercel deployment

1. Add this `frontend/` folder to the project repository.
2. Push to GitHub.
3. In Vercel, import the repository.
4. Set the project root directory to `frontend`.
5. Add environment variable `VITE_API_URL` with the public FastAPI backend URL.
6. Use build command `npm run build`.
7. Use output directory `dist`.

The frontend and backend can be deployed separately.
