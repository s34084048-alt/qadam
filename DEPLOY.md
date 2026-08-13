# Deploying QADAM to a permanent URL

**NOT A MEDICAL DEVICE — not for clinical use.** Anything reachable at the
resulting URL is on the public internet. Seed synthetic data only.

## One service, one URL

```
  phone / browser ──► container host
                        FastAPI + OpenCV + the built web bundle
                        SQLite + local files, both EPHEMERAL
```

The root `Dockerfile` builds the web app and the API into one image and serves
both from the same origin, so `/api` is same-origin: no CORS, and no bearer
token ever crosses an origin boundary. One host, one URL, nothing to proxy.

Splitting it later (static bundle on Vercel or Netlify, API elsewhere) is a
configuration change, not a code change: leave `SERVE_WEB_DIR` unset and put
the API hostname in `web/vercel.json`.

## Where it can and cannot run

The API needs a **container**. It imports OpenCV, holds a connection pool, and
spends real CPU per analysis.

| Host | Verdict |
| --- | --- |
| Render, free web service | Works. Sleeps after ~15 min idle. |
| Koyeb / Railway / Fly | Work. Railway and Fly want a card. |
| **Hugging Face Spaces** | **Docker Spaces now need a paid PRO plan.** Static Spaces are free but cannot run Python. |
| **Netlify / Vercel / GitHub Pages** | **Static hosting only.** They serve the UI; every `/api` call 404s. |

A static host gives a live URL where the interface renders and nothing works —
no sign-in, no analysis. The entire analysis is server-side Python: subject
segmentation, LAB colour statistics, `distanceTransform`, pupil measurement.

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

### 2. Deploy

**Render → New → Blueprint → select the repository → Apply.**

`render.yaml` describes one free web service built from the root `Dockerfile`,
generates the three secrets, and provisions no database — it runs on SQLite
inside the instance, so there is nothing that expires. The first build takes
5–10 minutes, mostly installing OpenCV.

Any other container host works the same way: build the root `Dockerfile`, set
`ENVIRONMENT=prod`, and supply `JWT_SECRET`, `SEED_ADMIN_PASSWORD` and
`SEED_CLINICIAN_PASSWORD`. The image reads `$PORT` and falls back to 7860.

### 3. Open access, if you want it

`DEMO_MODE=true` puts a **Start a demo session** button on the sign-in page:
one click, no password, no account.

It is safe to offer only because of what it does NOT share. Each visitor gets
their own organisation, so the isolation boundary that already exists keeps
their patients, cases and images invisible to every other visitor — and to the
seeded account. A single shared login would not do that, and on a tool like
this someone will eventually point it at a real patient: the people most likely
to try it are the people with patients in front of them.

The demo account holds a random password hash that nobody has, so it is not a
way in through `/auth/login`. It is a clinician, never an admin. Consent is
still enforced, and every disclaimer is unchanged.

Off unless you set it. With it off, `/auth/demo` answers 404 rather than 403 —
in a normal deployment that endpoint does not exist, and "forbidden" would
advertise that it could.

### 4. Confirm and sign in

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

- **Everything resets.** The database is SQLite and the images are on the
  container's own filesystem; a restart or a redeploy wipes both, and
  `SEED_ON_START=true` refills it with synthetic cases. Fine for a demo and
  for nothing else. For durability, attach a managed database and set
  `DATABASE_URL`, and set `STORAGE_BACKEND=s3` with the `S3_*` variables
  pointing at Cloudflare R2 — neither is a code change.
- **On a free instance the first visit is slow.** It sleeps after about 15
  minutes idle, and waking it plus importing OpenCV takes roughly a minute.
  If the link has to be instant when someone opens it — a live pitch — that is
  the one thing worth paying for.
- **It is still not validated.** A permanent URL changes nothing about that.
