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
    context = {"sync_max_students": settings.SYNC_SOLVE_MAX_STUDENTS}
    return render(request, 'index.html', context)