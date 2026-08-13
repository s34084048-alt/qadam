# Deploying QADAM to a permanent URL

**NOT A MEDICAL DEVICE — not for clinical use.** Anything reachable at the
resulting URL is on the public internet. Seed synthetic data only.

## Shape of it

```
  phone / browser
        │  https://qadam.vercel.app
        ▼
  Vercel  ── static React bundle
        │  /api/*  rewritten, same origin
        ▼
  container host ── FastAPI + OpenCV  ──►  managed Postgres
```

The web app talks to `/api` on **its own origin**; Vercel proxies that to the
API. So no CORS, and no bearer token ever crosses an origin boundary.

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

### 2. Deploy the API

Render (free-ish, `render.yaml` provisions the API and Postgres together):
New → Blueprint → select the repository. It reads `render.yaml`, generates
every secret, runs the migrations and seeds synthetic demo cases.

Railway is the smoother paid alternative (~$5/month, no cold starts): New →
Deploy from repo → root `api/`, add a Postgres plugin, and set the same
variables `render.yaml` lists.

Confirm it is alive:

```bash
curl https://<api-host>/api/v1/health
```

It must answer `"clinical_use": false`.

### 3. Point the web at it

In `web/vercel.json` replace `REPLACE-WITH-API-HOST` with the API hostname
(no scheme, no trailing slash), then deploy `web/` to Vercel.

### 4. Sign in

`ENVIRONMENT=prod` hides the demo-account panel, so the seeded credentials are
not printed on the login page. Read the generated `SEED_CLINICIAN_PASSWORD`
from the host's environment tab and sign in with `clinician@qadam.app`.

## What the deployment refuses to do

`app/config.py` will not start the process when `ENVIRONMENT` is `staging` or
`prod` and any of `JWT_SECRET`, `SEED_ADMIN_PASSWORD`,
`SEED_CLINICIAN_PASSWORD` or `S3_SECRET_KEY` is still at its shipped default.
Those defaults are printed in this repository, in `docker-compose.yml` and in
the README — reaching a public host with one of them set is a published
credential. A warning in a log nobody reads is not a control, so it fails to
boot instead.

## Known limits of this deployment

- **Images do not survive a restart.** `STORAGE_BACKEND=local` writes to the
  instance's own ephemeral filesystem. Fine for a demo, nothing else. For
  durability attach a disk, or set `STORAGE_BACKEND=s3` with the `S3_*`
  variables pointing at Cloudflare R2 or S3.
- **Render's free tier sleeps** after about 15 minutes idle; the next request
  waits roughly a minute while the container starts. If the link must be
  instant when someone opens it, use the paid tier or Railway.
- **It is still not validated.** A permanent URL changes nothing about that.
