from django.conf import settings
from django.shortcuts import render


def index(request, param=None):
    # SYNC_SOLVE_MAX_STUDENTS is handed to the frontend here (as
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
    context = {
        "sync_max_students": settings.SYNC_SOLVE_MAX_STUDENTS,
        "sync_tmax_default_seconds": settings.SYNC_SOLVE_TMAX_SECONDS,
        "sync_tmax_min_seconds": settings.SYNC_SOLVE_TMAX_MIN_SECONDS,
        "sync_tmax_max_seconds": settings.SYNC_SOLVE_TMAX_MAX_SECONDS,
    }
    return render(request, 'index.html', context)