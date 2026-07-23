# Deploying the Dashboard: Render (backend) + Vercel (frontend)

This app is a solo-admin tool. Deploying it makes it reachable from anywhere
you're logged in — it does **not** make it safe to leave undefended. Follow
every step, especially the credentials one.

## 1. Deploy the backend to Render

1. In the Render dashboard, create a new **Web Service** from this GitHub repo.
   If `render.yaml` at the repo root is still accurate (check it against
   Render's current Blueprint docs first — schemas drift), use "New Blueprint
   Instance" to create it from that file directly. Otherwise configure manually:
   - Root directory: `dashboard-app/backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/api/health`
2. Add a **Disk** (Render's persistent storage add-on — requires a paid
   instance type, not the free tier): mount path `/data`, 1 GB is plenty for
   this dataset size.
3. Set environment variables (Render dashboard → your service → Environment):
   - `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`,
     `WHATSAPP_TEMPLATE_LANG`, `EMAIL_SENDER`, `BREVO_API_KEY` — same values
     as your local `.env`.
   - `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` — **pick real, unique
     credentials now, not placeholders.** Anyone with these can read every
     client's name/email/phone number and trigger WhatsApp sends.
   - `DASHBOARD_DB_PATH=/data/clients.db` — points the app at the persistent
     disk instead of the ephemeral checkout path.
   - Leave `DASHBOARD_ALLOWED_ORIGIN` unset for now — you'll set it after
     step 2, once you know the Vercel URL.
4. Deploy. Confirm `https://<your-service>.onrender.com/api/health` returns
   `{"status": "ok"}`.

## 2. Get the real client data onto the Render disk

The disk starts empty — `clients.db` doesn't exist there yet. Recommended:
transfer the source spreadsheet (which you already treat as the source of
truth) and run the same migration script Render will run, rather than
copying the already-built `.db` file:

1. Open a shell on the Render service (Render dashboard → your service →
   "Shell").
2. Upload `clients_certifications.xlsx` to the service (Render's shell
   supports file upload via its web UI, or `scp`/`rsync` if you've set up
   SSH access — check Render's current docs for the supported method).
3. From the shell, at the repo root: `python dashboard-app/backend/migrate_to_sqlite.py`. It reads
   `clients_certifications.xlsx` and writes to `$DASHBOARD_DB_PATH`
   (`/data/clients.db`), verifying the row count matches before declaring
   success — the same script and safety check you already ran locally.
4. Confirm: `python -c "from db import read_clients, DEFAULT_DB_PATH; print(len(read_clients(DEFAULT_DB_PATH)))"`
   should print the same row count as your local `clients.db`.

## 3. Deploy the frontend to Vercel

1. Import this GitHub repo into Vercel as a new project.
2. Set the project's root directory to `dashboard-app/frontend`. Vercel's
   zero-config Vite detection handles the build command/output directory.
3. Add an environment variable: `VITE_API_BASE_URL` = your Render service's
   URL from step 1 (e.g. `https://absolute-veritas-dashboard-backend.onrender.com`,
   no trailing slash).
4. Deploy. Note the resulting Vercel URL (e.g.
   `https://absolute-veritas-dashboard.vercel.app`).

## 4. Close the loop: tell the backend about the frontend's origin

Back in Render (step 1's service) → Environment: set
`DASHBOARD_ALLOWED_ORIGIN` to the Vercel URL from step 3. Save — Render
redeploys automatically.

## 5. Verify end to end

1. Open the Vercel URL. You should land on the login screen (not the
   dashboard directly — if you see the dashboard immediately, `VITE_API_BASE_URL`
   likely wasn't set at build time; check step 3.2 and redeploy).
2. Sign in with the `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` you set in
   step 1.3. You should land on the dashboard with real client data loaded.
3. Confirm pagination, search, filters, and CSV export all work.
4. **Do not** test "Send Alert" / "Send All Eligible" against this deployment
   unless `DASHBOARD_TEST_NUMBER` is also set on Render to a verified test
   number — otherwise a test click sends a real WhatsApp message to a real
   client.

## Updating later

- Backend code changes: push to the branch Render is tracking; it redeploys
  automatically. `clients.db` on the disk is untouched by a redeploy.
- Frontend code changes: push to the branch Vercel is tracking; it redeploys
  automatically.
- Client roster changes: use the dashboard's own Excel Sync page (Replace or
  Merge) against the live deployment — no need to re-run the migration
  script or touch the Render shell again after the initial data load in
  step 2.
