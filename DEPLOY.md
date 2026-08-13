# Deploying QADAM to a permanent URL

**NOT A MEDICAL DEVICE — not for clinical use.** Anything reachable at the
resulting URL is on the public internet. Seed synthetic data only.

## Two ways, both single-origin

**Free, no card — one container serves everything (Hugging Face Spaces):**

```
  phone / browser ──► Space ── FastAPI + OpenCV + built web bundle
                               SQLite + local files, both EPHEMERAL
```

**Paid — split, with a real database:**

```
  phone / browser ──► Vercel (static bundle)
                        │  /api/* rewritten
                        ▼
                      container host ── FastAPI ──► managed Postgres
```

Either way the web app talks to `/api` on **its own origin**, so there is no
CORS and no bearer token ever crosses an origin boundary. In the first that is
because one process serves both; in the second because Vercel proxies.

Start with the free one. Nothing about the split version is a code change —
`SERVE_WEB_DIR` on or off is the whole difference.

## Why the API is not on Vercel too

It is a stateful, CPU-bound, container-shaped service. It imports OpenCV, holds
a connection pool, and spends real CPU per analysis. On serverless functions the
dependency bundle sits at the size limit and every cold start lands on top of
the analysis time. It already has a working `Dockerfile`; a container host runs
it unchanged.

## Steps

### 1. Put the code in a Git repository

Both hosts deploy from Git. From `qadam/`:

```bash
git init && git add -A && git commit -m "QADAM"
```

Then create an empty repository on GitHub and push to it.

The repository holds no real credentials — the passwords in the README and
`docker-compose.yml` are local development defaults, and the process refuses to
start on them in a public deployment (see below). So public or private is a
business decision, not a security one. What a public repository does change is
that anyone can clone this and stand it up: it is **not validated**, and the
boundary in the README and in every payload is what travels with it.

### 2a. Free: Hugging Face Spaces

Free, needs no payment card, and the URL stays up. On the free CPU tier a Space
sleeps only after about 48 hours idle and wakes on the next request.

1. Create an account at huggingface.co, then **New Space**:
   - SDK **Docker** → *blank*, hardware **CPU basic (free)**
2. Add the repository as a second remote and push:

   ```bash
   git remote add space https://huggingface.co/spaces/<user>/qadam
   git push space main
   ```

3. **Settings → Variables and secrets**, add three *secrets*:
   `JWT_SECRET`, `SEED_ADMIN_PASSWORD`, `SEED_CLINICIAN_PASSWORD` — any long
   random strings. The Space will not start without them; that is deliberate,
   see below.

The root `Dockerfile` builds the web bundle and the API into one image and
serves both on port 7860.

### 2b. Paid: split deployment

Put the API on any container host that takes a Dockerfile (Railway ≈ $5/month
is the smoothest; Render's blueprint is in `render.yaml`, but note its free
Postgres is deleted after 30 days and its free web service sleeps after 15
minutes). Build `api/Dockerfile`, attach a managed Postgres, and set the
variables listed in `render.yaml`. Leave `SERVE_WEB_DIR` unset.

Then in `web/vercel.json` replace `REPLACE-WITH-API-HOST` with the API
hostname, and deploy `web/` to Vercel.

### 3. Confirm and sign in

```bash
curl https://<host>/api/v1/health
```

It must answer `"clinical_use": false`.

`ENVIRONMENT=prod` hides the demo-account panel, so the seeded credentials are
not printed on the login page. Sign in as `clinician@qadam.app` with whatever
you set `SEED_CLINICIAN_PASSWORD` to.

## What the deployment refuses to do

`app/config.py` will not start the process when `ENVIRONMENT` is `staging` or
`prod` and any of `JWT_SECRET`, `SEED_ADMIN_PASSWORD`,
`SEED_CLINICIAN_PASSWORD` or `S3_SECRET_KEY` is still at its shipped default.
Those defaults are printed in this repository, in `docker-compose.yml` and in
the README — reaching a public host with one of them set is a published
credential. A warning in a log nobody reads is not a control, so it fails to
boot instead.

## Known limits of this deployment

- **On the free Space, everything resets.** The database is SQLite and the
  images are on the container's own filesystem; a restart or a rebuild wipes
  both, and `SEED_ON_START=true` refills it with synthetic cases. Fine for a
  demo and for nothing else. For durability move to 2b, or set
  `STORAGE_BACKEND=s3` with the `S3_*` variables pointing at Cloudflare R2.
- **Cold starts are slow.** OpenCV import plus the first analysis on a woken
  Space takes a few seconds. If the link must be instant, that is 2b.
- **It is still not validated.** A permanent URL changes nothing about that.
