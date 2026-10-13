# Deployment

MATE runs on AWS Lambda (function `mate-dev`), deployed with
[Zappa](https://github.com/zappa/Zappa) using `client/zappa_settings.json`.
Static assets are served from S3. Paths and commands below are relative
to this `code` folder.

## One-time setup

Install the Python version that matches the Lambda runtime (currently
`python3.12`, see `"runtime"` in `zappa_settings.json`) and configure an
AWS CLI profile matching its `"profile_name"` (currently `mate`). The
credentials need permission to manage the Lambda function, its S3 buckets
and its API Gateway.

```bash
brew install python@3.12
aws configure --profile mate
```

In the Lambda console (Configuration > Environment variables), set
`DJANGO_DEBUG` to `0`. It's set directly on the function rather than in
`zappa_settings.json`, because Zappa replaces all of the function's
environment variables on every deploy when that field is used.

The other environment variables (secret key, cluster credentials) are set
the same way. See `client/.env.example` for the full list.

## Every deploy

```bash
cd client
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt   # includes zappa
zappa update dev
```

`zappa update` doesn't upload static files. After a frontend rebuild or
any change to static assets, also run:

```bash
DJANGO_DEBUG=0 AWS_PROFILE=mate python manage.py collectstatic --noinput
```

`AWS_PROFILE` is needed here because `profile_name` in
`zappa_settings.json` is only read by Zappa, not by `collectstatic`.

### Package size

`slim_handler` is enabled in `zappa_settings.json`. The deployment package
(mostly `ortools` and its `pandas`/`numpy` dependencies) is over Lambda's
250 MB unzipped limit, so Zappa uploads it to S3 and unpacks it into `/tmp`
on cold start.

### Shared model code

`client` is deployed on its own, so it carries its own copy of
`model_common.py`, duplicated from `cluster`. If you change one copy,
change the other and run both test suites before deploying.
