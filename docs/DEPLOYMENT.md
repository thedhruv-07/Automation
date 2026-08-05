# Deploying the Dashboard: Render (backend) + Vercel (frontend)

This app is a solo-admin tool with **no login/authentication** — deploying it
makes the dashboard, all client PII (names/emails/phone numbers), and the
bulk-send buttons reachable by anyone with the URL. Only deploy it somewhere
not indexed/shared, or put access control in front of it (e.g. Vercel's own
password protection, an IP allowlist, or a VPN) if that matters to you.

> **Data lives in MongoDB Atlas + Wasabi, not on Render's filesystem.**
> Unlike the old SQLite setup, a Render restart/redeploy/spin-down-from-
> inactivity never wipes anything — the client roster, send-dedup logs, and
> notice logs are all in MongoDB; every uploaded Excel file is archived to
> Wasabi. No Render Disk, no reload-the-roster-after-every-restart routine.
>
> **One consequence worth being deliberate about**: if your local `.env`'s
> `MONGODB_URI` points at the same Atlas cluster/database as Render's, local
> dev and production are *the same database*. A test upload from your
> laptop shows up in production immediately, and vice versa. If that's not
> what you want, create a second database (Atlas lets you point different
> connection strings at different database names within one free-tier
> cluster) and use it locally instead.

## 1. Set up MongoDB Atlas and Wasabi

1. **MongoDB Atlas**: create a free-tier (M0) cluster if you don't have one.
   Under **Network Access**, add the IP address of every machine that needs
   to connect (your local dev machine, and — since Render's outbound IPs
   aren't static on the free tier — `0.0.0.0/0` for Render specifically,
   accepting that this means "any IP" can attempt to connect, though they
   still need the real username/password to authenticate). Under
   **Database Access**, create a user and note the username/password. Get
   the connection string (**Connect → Drivers**) — it looks like
   `mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?appName=...`.
2. **Wasabi**: create a bucket in the Wasabi console, and an access
   key/secret key pair (**Access Keys** in the console). Note the region's
   S3-compatible endpoint URL (e.g. `https://s3.us-central-1.wasabisys.com`
   — check your bucket's actual region in the console, this varies).

## 2. Deploy the backend to Render

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
   - `MONGODB_URI` — from step 1 above (decide deliberately whether this is
     the same database your local `.env` uses, per the warning above).
   - `WASABI_ACCESS_KEY`, `WASABI_SECRET_KEY`, `WASABI_BUCKET`,
     `WASABI_ENDPOINT` — from step 1 above.
   - Leave `DASHBOARD_ALLOWED_ORIGIN` unset for now — you'll set it after
     step 4, once you know the Vercel URL.
3. Deploy. Confirm `https://<your-service>.onrender.com/api/health` returns
   `{"status": "ok"}`.
4. Confirm the MongoDB connection actually works (not just that the process
   started — `pymongo` connects lazily, so a bad `MONGODB_URI` won't fail
   at startup, only on the first real request):
   `curl https://<your-service>.onrender.com/api/stats` should return real
   JSON (a `status_counts` object), not hang or time out. If it hangs, the
   most common cause is Atlas's Network Access list not including
   `0.0.0.0/0` (or Render's actual outbound IP, if you've pinned it down) —
   see step 1.

## 3. Load real client data

Since the roster now lives in MongoDB (not a per-deployment file), there's
no separate "push data onto the server" step distinct from what you'd do
locally — use the dashboard's own **Excel Sync → Replace** page, either
against your local dev instance or the deployed one, whichever database
you want to populate (remember: if they share one `MONGODB_URI`, either one
populates both).

## 4. Deploy the frontend to Vercel

1. Import this GitHub repo into Vercel as a new project.
2. Set the project's root directory to `dashboard-app/frontend`. Vercel's
   zero-config Vite detection handles the build command/output directory.
3. Add an environment variable: `VITE_API_BASE_URL` = your Render service's
   URL from step 2 (e.g. `https://absolute-veritas-dashboard-backend.onrender.com`,
   no trailing slash).
4. Deploy. Note the resulting Vercel URL (e.g.
   `https://absolute-veritas-dashboard.vercel.app`).

## 5. Close the loop: tell the backend about the frontend's origin

Back in Render (step 2's service) → Environment: set
`DASHBOARD_ALLOWED_ORIGIN` to the Vercel URL from step 4. Save — Render
redeploys automatically.

## 6. Verify end to end

1. Open the Vercel URL. You should land directly on the dashboard with real
   client data loaded — there's no login screen.
2. Confirm pagination, search, filters, and CSV export all work.
3. **Do not** test "Send Alert" / "Send All Eligible" (WhatsApp) or "Send
   Email" / "Send All Emails" against this deployment unless
   `DASHBOARD_TEST_NUMBER` / `DASHBOARD_TEST_EMAIL` are also set on Render to
   a verified test number/address — otherwise a test click sends a real
   message to a real client.

## Updating later

- Backend code changes: push to the branch Render is tracking; it redeploys
  automatically. Data is untouched by this — it's in MongoDB, not on
  Render's filesystem.
- Frontend code changes: push to the branch Vercel is tracking; it redeploys
  automatically.
- Client roster changes day-to-day: use the dashboard's own Excel Sync page
  (Replace or Merge) against whichever environment you're updating — the
  change is immediately visible everywhere pointed at the same
  `MONGODB_URI`.
- Wasabi archives accumulate over time (one object per upload) — there's no
  automatic cleanup; periodically review the bucket if storage cost matters
  to you.
