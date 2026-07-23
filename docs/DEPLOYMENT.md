# Deploying the Dashboard: Render (backend) + Vercel (frontend)

This app is a solo-admin tool. Deploying it makes it reachable from anywhere
you're logged in — it does **not** make it safe to leave undefended. Follow
every step, especially the credentials one.

> **You're on Render's free tier: `clients.db` will NOT persist.** Free-tier
> services have an ephemeral filesystem and spin down after inactivity,
> wiping local files when they restart. Every time that happens, the roster
> is gone until you reload it (Step 2, or the dashboard's own Excel Sync
> page). There is no code difference between free and paid here — `db.py`
> already supports a `DASHBOARD_DB_PATH` override for a persistent disk;
> upgrading later is just adding that env var and a Render Disk, no redeploy
> of new code required. Until then, treat this deployment as something you
> reload data into each time you start using it after a gap, not a
> fire-and-forget system of record.

## 1. Deploy the backend to Render

1. In the Render dashboard, create a new **Web Service** from this GitHub repo.
   If `render.yaml` at the repo root is still accurate (check it against
   Render's current Blueprint docs first — schemas drift), use "New Blueprint
   Instance" to create it from that file directly. Otherwise configure manually:
   - Root directory: `dashboard-app/backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/api/health`
   - Instance type: free
2. Set environment variables (Render dashboard → your service → Environment):
   - `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`,
     `WHATSAPP_TEMPLATE_LANG`, `EMAIL_SENDER`, `BREVO_API_KEY` — same values
     as your local `.env`.
   - `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` — **pick real, unique
     credentials now, not placeholders.** Anyone with these can read every
     client's name/email/phone number and trigger WhatsApp sends.
   - Leave `DASHBOARD_ALLOWED_ORIGIN` unset for now — you'll set it after
     step 2, once you know the Vercel URL.
   - Do **not** set `DASHBOARD_DB_PATH` — with no persistent disk attached,
     the default (`data/clients.db` inside the ephemeral checkout) is exactly
     as durable as any path you'd point it at instead.
3. Deploy. Confirm `https://<your-service>.onrender.com/api/health` returns
   `{"status": "ok"}`.

## 2. Load real client data onto the running service

Because the filesystem is ephemeral, this step needs repeating after every
restart/redeploy/spin-down (see the warning above) — bookmark it rather than
treating it as a one-time setup step:

1. Open a shell on the Render service (Render dashboard → your service →
   "Shell").
2. Upload `data/clients_certifications.xlsx` to the service (Render's shell
   supports file upload via its web UI, or `scp`/`rsync` if you've set up
   SSH access — check Render's current docs for the supported method). Put
   it at `data/clients_certifications.xlsx` relative to the repo root, matching
   where `migrate_to_sqlite.py` expects to find it.
3. From the shell, at the repo root: `python dashboard-app/backend/migrate_to_sqlite.py`. It reads
   `data/clients_certifications.xlsx` and writes to `data/clients.db`,
   verifying the row count matches before declaring success — the same
   script and safety check you already ran locally. If a previous
   `clients.db` from before the last restart happens to still be present
   (it won't be, on a genuine restart, but might be after a code-only
   redeploy) and already has rows, this refuses to run — pass `--force`
   only if you're deliberately overwriting it.
4. Confirm: `python -c "from db import read_clients, DEFAULT_DB_PATH; print(len(read_clients(DEFAULT_DB_PATH)))"`
   should print the same row count as your local `clients.db`.

**Faster alternative for routine reloads**: once the service is up, you can
skip the shell entirely and use the dashboard's own **Excel Sync → Replace**
page instead (upload `clients_certifications.xlsx` through the browser) —
same effect, no shell access needed. The shell + migration script route
above is only necessary the first time, or if you specifically want the
`migrate_to_sqlite.py` script's row-count verification.

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
  automatically. **On the free tier, a redeploy likely wipes `clients.db`**
  (new container, ephemeral filesystem) — reload the data afterward via
  Step 2's Excel Sync shortcut.
- Frontend code changes: push to the branch Vercel is tracking; it redeploys
  automatically.
- Client roster changes day-to-day: use the dashboard's own Excel Sync page
  (Replace or Merge) against the live deployment. Just remember that on the
  free tier this only lasts until the next restart/spin-down — it's not a
  substitute for keeping your local `data/clients_certifications.xlsx` as
  the real source of truth.
- If you later upgrade to a paid instance + Render Disk: add a `disk:` block
  back to `render.yaml` (or the dashboard equivalent) and set
  `DASHBOARD_DB_PATH` to its mount path (e.g. `/data/clients.db`) as an env
  var. No code changes needed — `db.py` already supports this, it's exactly
  what this setup used before switching to the free tier.
