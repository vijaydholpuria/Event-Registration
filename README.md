# EventHub deployment

The project is split into a static Vercel frontend and a Flask API on Render. The backend continues to connect directly to the existing Supabase PostgreSQL database; no schema or record migration is part of this deployment.

## Vercel frontend

1. Import the repository into Vercel and set the project Root Directory to `frontend`.
2. Use the Other framework preset. The static files are the build output; no package installation or build command is required.
3. Set the deployment's custom domain (for example, `https://app.example.com`).
4. After the Render service is created, replace `YOUR-RENDER-SERVICE` in `frontend/config.js` with the Render API hostname. This is a public API URL, not a credential.

`frontend/vercel.json` maps the existing page paths, including event and ticket paths, to their static HTML files.

## Render backend

Deploy using `backend/render.yaml` (or set the Render service Root Directory to `backend`). It installs `backend/requirements.txt`, runs `gunicorn app:app`, and exposes `/api/health` as its health check.

Set the environment variables listed in `backend/.env.example` in Render. `DATABASE_URL` must be the existing Supabase PostgreSQL connection string. Set `FRONTEND_URL` to the Vercel custom-domain origin and `ALLOWED_ORIGINS` to that exact origin. Set `UPI_ID` to the existing payment recipient. The frontend configuration contains no secret values.

The Render blueprint attaches a persistent disk at `/var/data`; uploads and generated QR files are saved in `/var/data/uploads`. The disk is required to retain profile/event uploads and tickets across service restarts. Confirm the selected Render plan supports persistent disks before deployment.

Use same-site custom subdomains for the two services (for example, `app.example.com` and `api.example.com`). The backend retains Flask's signed, HttpOnly session cookie; `Secure` is enabled and `SameSite=Lax` is configured for HTTPS deployments.

## Supabase and data

Keep the existing Supabase PostgreSQL project and configure only its connection string in Render. This deployment does not run schema migrations, create tables, or delete or rewrite existing records.

## Smoke checks

After both services deploy, check `/api/health`, then exercise OTP signup/verification, login/logout, dashboard events, admin event create/delete and registration list, free and paid registration, UPI QR/confirmation, ticket scan, profile update/image upload, registration history, and contact email. Verify media survives a Render restart and that the browser session remains authenticated between frontend and API.
