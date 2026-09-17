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
- **Sensitivity analysis on a feasible solve, too**: the same deletion-filter
  mechanism runs on demand after a *successful* solve to report which
  constraint family is costing the most #1-choice placements if relaxed --
  the complementary question to infeasibility diagnosis.
- **A user-adjustable, server-clamped solve-time budget**: the person
  running a solve picks their own time budget for the in-request CP-SAT
  path; the server always clamps it to a configured floor/ceiling before
  it reaches the solver, so a stale or crafted request can't ask for more
  time than the deployment allows.

See **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** for the full
technical write-up (stack, the CP-SAT formulation, preprocessing, the
warm-start heuristic and its benchmarks, and the sync/async split).

## Stack

- **Backend**: Django + Django REST Framework, deployed to AWS Lambda via
  [Zappa](https://github.com/zappa/Zappa). Static assets are served from
  S3 in production.
- **Solver**: [OR-Tools](https://developers.google.com/optimization) CP-SAT
  (`code/client/backend/optimization_cpsat.py`, open-source, runs
  in-process for small rosters) for the sync path, Gurobi
  (`code/server/optimization.py`) on a Slurm cluster via SSH for large
  rosters -- two independently maintained implementations of the same
  formulation, not a runtime-configurable choice (see `model_common.py`'s
  module docstring).
- **Frontend**: React (bundled with Webpack) served by the Django template
  in `code/client/frontend/`.
- **CI**: GitHub Actions runs the Django system check, the solver's test
  suite, and lints + production-builds the frontend on every push/PR
  (`.github/workflows/ci.yml`).

## Project layout

```
code/
  client/       Django project (backend API + served frontend) — a
                self-contained, independently deployed project
    project/    Django settings, root urls
    backend/    REST API views (upload, run_model), the CP-SAT solver
                (optimization_cpsat.py), and its own copy of model_common.py
    frontend/   React app source (frontend/src) + built bundle (frontend/static)
  server/       The Gurobi optimizer — its own independent copy of
                model_common.py, plus optimization.py; runs standalone on
                the cluster for large jobs, reached only over SSH by
                code/client/backend/utils.py's upload_parms() -- never
                imported in-process by code/client (see model_common.py's
                module docstring)
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

### 3. The solver test suites

Two independent suites, matching the two independent codebases (see
[Stack](#stack) and `model_common.py`'s module docstring): neither
imports the other.

`code/server/tests/` covers `model_common.py`'s preprocessing, from
`code/server`'s own copy:

```
cd code/server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

`code/client/backend/tests/` covers model building/solving and
postprocessing (`optimization_cpsat.py`), plus `code/client`'s own copy
of `model_common.py`, using the venv you already set up in step 1 (or a
fresh one -- either way, `pytest` needs adding via `requirements-dev.txt`,
which layers on top of `requirements.txt`):

```
cd code/client
pip install -r requirements-dev.txt
pytest backend/tests/test_model_solving.py backend/tests/test_postprocessing.py -v
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
| `MATE_SYNC_MAX_STUDENTS` / `MATE_SYNC_TMAX_SECONDS` | Threshold/default time-budget for solving synchronously in-request vs. handing off to the cluster -- the frontend's Sync/Async indicator and solve-time slider read these at page load via `window.__MATE_CONFIG__` (see `frontend/views.py`), so they're each a single value, not a constant duplicated on both sides | 100 / 20s | same |
| `MATE_SYNC_TMAX_MIN_SECONDS` / `MATE_SYNC_TMAX_MAX_SECONDS` | Floor/ceiling the server clamps the sync solve-time slider to, regardless of what the client sends | 5s / 25s | same |
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
2. Add both `http://localhost:8000/dev/auth/callback` (local dev) and your
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
- **`code/client/model_common.py`** is a real, committed file, not
  generated at deploy time — `code/client` is fully self-contained, so
  Zappa zipping up only that directory (the directory it's run from) is
  enough on its own; there's no sibling directory it needs to reach into.
  It's a hand-duplicated copy of `code/server/model_common.py`, kept in
  sync by hand rather than shared via import — see that file's module
  docstring for why. If you change one copy, change the other and rerun
  both test suites ([step 3](#3-the-solver-test-suites)) before deploying.
- Large-roster (offline) runs need the cluster SSH credentials set as
  Lambda environment variables too, if you're using that path in production.

## License

[MIT](LICENSE)
