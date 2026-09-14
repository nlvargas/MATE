"""
Sign-in endpoints for the cluster-access gate -- see msft_auth.py's module
docstring for the full picture. Plain Django views (not DRF): login/logout/
callback are browser navigations (redirects), not JSON API calls, and none
of them need DRF's request-parsing/content-negotiation machinery.
"""
from django.http import HttpResponseRedirect, JsonResponse

from . import msft_auth


def login(request):
    if not msft_auth.is_configured():
        return JsonResponse(
            {
                "error": "not_configured",
                "message": (
                    "Microsoft sign-in isn't configured on this deployment "
                    "(MS_CLIENT_ID / MS_CLIENT_SECRET aren't set)."
                ),
            },
            status=503,
        )
    return HttpResponseRedirect(msft_auth.start_login(request))


def auth_callback(request):
    email, error = msft_auth.complete_login(request)
    if error:
        request.session["mate_auth_error"] = error
    else:
        request.session["mate_user_email"] = email
    # Back to the SPA's one page; it reads the outcome via GET /auth/status
    # on load rather than through the URL, so this redirect stays simple.
    return HttpResponseRedirect("/")


def logout(request):
    request.session.pop("mate_user_email", None)
    return HttpResponseRedirect("/")


def status(request):
    email = request.session.get("mate_user_email")
    return JsonResponse({
        "authenticated": msft_auth.session_email_allowed(request.session),
        "email": email,
        # Popped, not just read: a sign-in error should reach the frontend
        # once, right after the redirect that caused it, not linger and
        # reappear on every later status poll from the same browser session.
        "error": request.session.pop("mate_auth_error", None),
        "configured": msft_auth.is_configured(),
    })
