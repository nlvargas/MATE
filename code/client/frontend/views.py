from django.conf import settings
from django.shortcuts import render


def _api_base(request):
    """
    URL prefix the frontend puts in front of /upload/, /run_model/ and
    /sensitivity/. Locally (DEBUG) the backend routes are mounted under
    /dev/ (see project/urls.py). Deployed, they live at the root of
    whatever origin serves the page: the custom domain maps straight onto
    the stage (so no prefix), while the default execute-api URL carries
    the stage name, which Zappa passes along as SCRIPT_NAME.
    """
    api_base = (request.META.get("SCRIPT_NAME") or "").rstrip("/")
    if settings.DEBUG:
        api_base += "/dev"
    return api_base


def index(request, param=None):
    # SYNC_SOLVE_MAX_VARIABLES is handed to the frontend here (as
    # window.__MATE_CONFIG__ in index.html) instead of being duplicated as
    # a second hardcoded constant in CreateGroups.js -- see the comment on
    # that setting in project/settings.py. This is the one and only place
    # that number is written down; the "Sync"/"Async" indicator on the
    # Configure & run screen reads it from window.__MATE_CONFIG__ at
    # runtime, so it can never drift from what the backend will actually do.
    #
    # sync_tmax_default_seconds/min/max are the same idea applied to the new
    # user-adjustable solve-time slider (CreateGroups.js): the slider's
    # bounds and starting value come from here so they can never drift from
    # the clamp backend/views.py's run_model() actually enforces -- see
    # SYNC_SOLVE_TMAX_SECONDS/MIN/MAX's comments in project/settings.py.
    api_base = _api_base(request)
    context = {
        "api_base": api_base,
        "sync_max_variables": settings.SYNC_SOLVE_MAX_VARIABLES,
        "sync_tmax_default_seconds": settings.SYNC_SOLVE_TMAX_SECONDS,
        "sync_tmax_min_seconds": settings.SYNC_SOLVE_TMAX_MIN_SECONDS,
        "sync_tmax_max_seconds": settings.SYNC_SOLVE_TMAX_MAX_SECONDS,
    }
    return render(request, 'index.html', context)