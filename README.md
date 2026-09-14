# MATE — Make A Team Efficiently

[![CI](https://github.com/nlvargas/MATE/actions/workflows/ci.yml/badge.svg)](https://github.com/nlvargas/MATE/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MATE automatically splits a roster of students into balanced groups. Upload
a spreadsheet of students (their attributes and preferences), configure how
many groups you want and what should be balanced or bounded, and MATE runs
a constraint solver to produce an assignment — respecting section capacity,
target group sizes, per-attribute balance, and each student's stated
preferences as far as possible.

<p align="center">
  <img src="docs/images/03_configure.png" width="49%" alt="Configure & run screen" />
  <img src="docs/images/04_results.png" width="49%" alt="Results screen" />
</p>

## Why this is more than a CRUD app

This isn't roster storage with a form on top — the actual problem (assign
students to groups honoring capacity, balance and preference constraints
simultaneously) is a genuine constraint-satisfaction problem, modeled and
solved as one:

- **A real CP-SAT (Google OR-Tools) formulation** in
  [`code/client/backend/optimization_cpsat.py`](code/client/backend/optimization_cpsat.py) —
  sets, decision variables, and hard/soft constraints for group size,
  section capacity, per-attribute balance bounds, and preference ranking,
  minimized as a weighted objective.
- **Symmetry reduction before solving**: students who share the same
  attributes/preferences/availability are collapsed into one "student type"
  (`model_common.py`), so the model has one variable per (type, group) pair
  instead of one per (student, group) pair, then results are expanded back
  into real student assignments afterwards.
- **A warm-start heuristic** (`_greedy_hint()`) that's benchmarked, not
  assumed — measured ~23% faster on a synthetic 400-student roster; a
  symmetry-breaking alternative was also implemented, measured, and
  rejected (it made large solves ~4x slower) rather than left in on faith.
- **Actual infeasibility diagnosis**: when a configuration is infeasible,
  a deletion-filter search re-solves with one user-configurable constraint
  family removed at a time to report which specific bound is the problem,
  instead of a generic "try loosening your settings" message.

See **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** for the full
technical write-up (stack, the CP-SAT formulation, preprocessing, the
warm-start heuristic and its benchmarks, and the sync/async split).

## Stack

- **Backend**: Django + Django REST Framework, deployed to AWS Lambda via
  [Zappa](https://github.com/zappa/Zappa). Static assets are served from
  S3 in production.
- **Solver**: [OR-Tools](https://developers.google.com/optimization) CP-SAT
  (`code/client/backend/optimization_cpsat.py`, the open-source default,
  runs in-process for small rosters) or Gurobi (`code/server/optimization.py`,
  an optional swap-in, runs on a Slurm cluster via SSH for large rosters).
- **Frontend**: React (bundled with Webpack) served by the Django template
  in `code/client/frontend/`.
- **CI**: GitHub Actions runs the Django system check, the solver's test
  suite, and lints + production-builds the frontend on every push/PR
  (`.github/workflows/ci.yml`).

## Project layout

```
code/
  client/       Django project (backend API + served frontend)
    project/    Django settings, root urls
    backend/    REST API views (upload, run_model)
    frontend/   React app source (frontend/src) + built bundle (frontend/static)
  server/       The optimizer itself — model_common.py, optimization_cpsat.py,
                optimization.py (Gurobi variant); runs standalone on the cluster
                for large jobs, or is imported directly by backend/ for small ones
docs/
  ARCHITECTURE.md   Technical deep-dive + screenshots
```

## Running locally

### 1. Backend

```
cd code/client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the env template and fill in real values (a long random string is
fine for `DJANGO_SECRET_KEY` locally; the cluster credentials are only
needed if you're testing the large-roster/offline path):

```
cp .env.example .env
```

Run the dev server:

```
DJANGO_DEBUG=1 python manage.py runserver
```

`DJANGO_DEBUG` defaults on if unset, so for local dev you can usually just
run `python manage.py runserver` directly — see [Environment variables](#environment-variables)
below for what this actually controls.

### 2. Frontend

The built bundle (`frontend/static/main.js`, `frontend/static/theme.css`)
is what Django actually serves — you need to (re)build it after any
frontend change:

```
cd code/client/frontend
npm install
npm run dev      # development build, rebuild after each change
# or: npm run build   # production/minified build
npm run lint      # eslint (rules-of-hooks + exhaustive-deps included)
```

Webpack 4's build here predates Node's OpenSSL 3 default and needs the
legacy provider on modern Node (18+):

```
NODE_OPTIONS=--openssl-legacy-provider npm run build
```

With the backend running (`DEBUG=1`), open `http://127.0.0.1:8000/` — the
wizard should load: Setup → Upload → Configure & run → Results.

### 3. The solver test suite

`code/server/tests/` covers the whole optimization core -- preprocessing
(`model_common.py`), and model building/solving and postprocessing
(`optimization_cpsat.py`, which actually lives in `code/client/backend/`
since only the Django app runs it -- see [Stack](#stack)). Run it with
`code/server`'s `requirements-dev.txt`, which pulls in `ortools` just for
these tests (the cluster-side runtime doesn't need it):

```
cd code/server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

### 4. End-to-end smoke test

`backend/tests/e2e_smoke_test.py` drives the real HTTP API the same way
the frontend does -- `/upload/` then `/run_model/` -- for a synthetic
50-student roster, and checks every student actually gets placed. Point it
at a running server, local or deployed:

```
cd code/client
pip install -r backend/tests/requirements-e2e.txt
python3 backend/tests/e2e_smoke_test.py --base-url http://127.0.0.1:8000/dev
# or, after deploying:
python3 backend/tests/e2e_smoke_test.py --base-url https://<your-deployed-host>/dev
```

Not part of CI (there's no live server for CI to point it at) -- run it
by hand after a deploy, or anytime you want to check the whole request
path rather than just the solver.

## Environment variables

Set via `code/client/.env` locally (git-ignored, loaded by
`project/settings.py` through `django-environ`), or as Lambda environment
variables in production (see [Deploying](#deploying)):

| Variable | Purpose | Local default | Production |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Django's `SECRET_KEY` | insecure placeholder | set a real value |
| `DJANGO_DEBUG` | Toggles `DEBUG`, which also controls where static files are served from (local disk vs. S3) and how backend routes are mounted (see comment in `settings.py`) | on (`1`) | **must be `"0"`** |
| `MATE_CLUSTER_HOST` / `_USER` / `_PASSWORD` / `_PARAMS_PATH` | SSH access to the PUC compute cluster for large (offline) solves | — | required if using the offline path |
| `MATE_SOLVER` | `cpsat` (default, open-source) or `gurobi` (needs a license) | `cpsat` | `cpsat` |
| `MATE_SYNC_MAX_STUDENTS` / `MATE_SYNC_TMAX_SECONDS` | Threshold/time-budget for solving synchronously in-request vs. handing off to the cluster -- the frontend's Sync/Async indicator reads `MATE_SYNC_MAX_STUDENTS` at page load via `window.__MATE_CONFIG__` (see `frontend/views.py`), so it's a single value, not a constant duplicated on both sides | 100 / 20s | same |
| `MS_CLIENT_ID` / `MS_CLIENT_SECRET` / `MS_REDIRECT_URI` | Microsoft sign-in, gating who can submit a job to the cluster (see [Cluster sign-in](#cluster-sign-in-microsoft) below) | unset -- cluster submission returns a clear "not configured" error | required to allow any cluster submissions at all |
| `MATE_ALLOWED_EMAIL_DOMAINS` | Comma-separated email domains allowed to submit to the cluster | `uc.cl,ing.puc.cl` | same, or your own |

### Cluster sign-in (Microsoft)

The sync/CP-SAT path is open to anyone -- it's free, open-source, and runs
on this app's own Lambda. The cluster path spends a shared, licensed
resource (the PUC cluster's Gurobi seat and compute), so `backend/views.py`'s
large-roster branch is gated on signing in with a `uc.cl` or `ing.puc.cl`
account. The domain check happens in this app (`backend/msft_auth.py`), not
via Azure tenant restriction, on purpose -- see that file's module
docstring for the reasoning.

This needs an actual Microsoft/Azure app registration, which is an account
action, not something committed to this repo:

1. [portal.azure.com](https://portal.azure.com) -> Microsoft Entra ID ->
   App registrations -> New registration. Supported account types:
   "Accounts in any organizational directory".
2. Add both `http://127.0.0.1:8000/dev/auth/callback` (local dev) and your
   deployed `.../dev/auth/callback` URL as Web Redirect URIs.
3. Certificates & secrets -> New client secret -- copy its value
   immediately, Azure only shows it once.
4. Set `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, and `MS_REDIRECT_URI` (whichever
   of the two redirect URIs applies to that environment) in
   `code/client/.env` locally, or as Lambda environment variables in
   production, the same way the cluster SSH credentials already work.

Until those are set, `/dev/auth/login` returns a 503 instead of crashing,
and the frontend shows a "sign-in isn't configured" message in place of
the sign-in button when a roster is large enough to need it.

## Deploying

The app deploys to AWS Lambda (function `mate-dev`) via Zappa, using the
config in `code/client/zappa_settings.json`.

### One-time setup

Install a Python version matching the Lambda runtime (`zappa_settings.json`'s
`"runtime"`, currently `python3.12`) and configure an AWS CLI profile
matching `zappa_settings.json`'s `"profile_name"` (currently `mate`) with
credentials for an IAM user/role that can manage this Lambda function, its
S3 buckets, and its API Gateway:

```
brew install python@3.12       # if you don't already have it
aws configure --profile mate   # needs an AWS Access Key ID + Secret
```

**In the Lambda console** (Configuration → Environment variables), make
sure `DJANGO_DEBUG` is set to `"0"` — this isn't managed through
`zappa_settings.json` (which would replace *all* existing environment
variables on the function on every deploy, wiping anything set elsewhere)
so it's set directly on the function instead, once.

### Every deploy

```
cd code/client
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt   # includes zappa itself
zappa update dev
```

If you changed any static assets (frontend rebuild, `theme.css`, etc.),
also push them to S3 — `zappa update` does **not** do this for you:

```
DJANGO_DEBUG=0 AWS_PROFILE=mate python manage.py collectstatic --noinput
```

(`AWS_PROFILE` here is separate from `zappa_settings.json`'s
`profile_name` — that field is only read by Zappa itself; the actual
`collectstatic` command needs the profile set for its own AWS calls.)

### Notes

- **`slim_handler`** is enabled in `zappa_settings.json` — the deployment
  package (mainly `ortools`, which pulls in `pandas`/`numpy`) exceeds
  Lambda's 250MB unzipped code-size limit, so Zappa uploads the real
  package to S3 and unpacks it into `/tmp` at cold start instead.
- **`code/client/model_common.py`** (gitignored, not something you edit)
  is generated automatically on every deploy by `deploy_hooks.py`, wired
  in via `zappa_settings.json`'s `"callbacks": {"zip": ...}`. It's a copy
  of `code/server/model_common.py`, needed because Zappa only zips up
  `code/client/` — the directory it's run from — so the *sibling*
  `code/server/` directory (where the real `model_common.py` lives, shared
  with the Gurobi/cluster backend) would otherwise never make it into the
  Lambda package, even though `backend/utils.py` and
  `backend/optimization_cpsat.py` both import it. If that import fails,
  Django fails to even load its URLconf, so *every* route 500s — including
  a bare `GET /`, which is exactly the failure Zappa's own post-deploy
  health check exercises. You shouldn't need to do anything for this —
  it runs automatically as part of `zappa update dev` — but if you ever
  see `ModuleNotFoundError: No module named 'model_common'` in
  `zappa tail dev`, that's this callback not having run (e.g. because
  something invoked Zappa's packaging without going through the `zip`
  callback).
- Large-roster (offline) runs need the cluster SSH credentials set as
  Lambda environment variables too, if you're using that path in production.

## License

[MIT](LICENSE)
