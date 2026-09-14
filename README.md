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
- Large-roster (offline) runs need the cluster SSH credentials set as
  Lambda environment variables too, if you're using that path in production.

## License

[MIT](LICENSE)
