"""
Microsoft sign-in (Entra ID / Azure AD), restricted by email domain --
whether the currently-authenticated session is allowed to submit a job to
the PUC cluster.

Only backend/views.py's run_model() large-roster branch (the one that
actually calls upload_parms() and spends the cluster's Gurobi seat/compute)
is gated by this. The small/sync CP-SAT path stays open to anyone, on
purpose -- it's free, open-source, and runs on this app's own Lambda, so
there's nothing to protect there. See docs/ARCHITECTURE.md for the reasoning.

-------------------- One-time setup (can't be done from a coding session) --------------------
This needs an actual Microsoft/Azure app registration -- an account and
portal action, not something a coding assistant can do on your behalf:

  1. https://portal.azure.com -> "Microsoft Entra ID" -> "App registrations"
     -> "New registration".
     - Supported account types: "Accounts in any organizational directory"
       (Any Microsoft Entra ID tenant). This excludes personal Microsoft
       accounts (outlook.com/hotmail/live) before the domain check below
       even runs, and -- deliberately -- does NOT require registering the
       app inside uc.cl's own tenant (which would need app-registration
       rights there). See "Why app-level, not tenant-level" below.
     - Redirect URI (platform: "Web"): add BOTH
       http://127.0.0.1:8000/dev/auth/callback (local dev) and your
       deployed .../dev/auth/callback URL. Azure matches these literally,
       not by prefix, so they have to be exact.
  2. "Certificates & secrets" -> "New client secret". Copy the secret's
     VALUE (not its ID) immediately -- Azure only ever shows it once.
  3. Put the "Application (client) ID" from the Overview page and that
     secret value into code/client/.env as MS_CLIENT_ID / MS_CLIENT_SECRET
     (see .env.example), or as Lambda environment variables in production,
     the same way MATE_CLUSTER_PASSWORD etc. already work. Also set
     MS_REDIRECT_URI there to whichever one of the two URIs above applies
     to that environment.

Until MS_CLIENT_ID/MS_CLIENT_SECRET are set, is_configured() is False and
auth_views.login() returns a clear 503 instead of a confusing crash.

-------------------- Why app-level, not tenant-level --------------------
Azure *can* restrict sign-in to one specific tenant ("single tenant" apps),
which would be a stronger guarantee than a string check here -- but doing
that means the app registration itself has to live inside uc.cl's Entra
tenant, which this project shouldn't assume it has the standing to set up
(that's an IT/admin action, not a developer one). Registering as
multi-organization and checking the signed-in email's domain here gets the
same practical restriction (only uc.cl/ing.puc.cl accounts can submit a
cluster job) without that dependency. This is exactly as strong as trusting
Microsoft's own ID token claims, which is the standard trust boundary for
this kind of sign-in.
"""
import msal

from django.conf import settings


def _allowed_domains():
    return {
        d.strip().lower()
        for d in settings.MATE_ALLOWED_EMAIL_DOMAINS.split(",")
        if d.strip()
    }


MS_SCOPES = ["User.Read"]


def is_configured():
    return bool(settings.MS_CLIENT_ID and settings.MS_CLIENT_SECRET)


def _msal_app():
    return msal.ConfidentialClientApplication(
        settings.MS_CLIENT_ID,
        authority=settings.MS_AUTHORITY,
        client_credential=settings.MS_CLIENT_SECRET,
    )


def email_domain_allowed(email):
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[-1].strip().lower() in _allowed_domains()


def session_email_allowed(session):
    """
    The one check views.py's run_model() actually needs: is *this session*
    currently signed in as an account whose email domain is still allowed?
    Re-checking the domain here (not just "is an email present") means
    editing MATE_ALLOWED_EMAIL_DOMAINS takes effect for everyone
    immediately, without needing to invalidate any existing session.
    """
    return email_domain_allowed(session.get("mate_user_email"))


def start_login(request):
    """
    Kicks off the MSAL authorization-code flow (with PKCE + state + nonce,
    all handled by msal itself) and stashes the flow's own state in the
    session so complete_login() can verify the callback against it. Returns
    the Microsoft URL to redirect the browser to.
    """
    flow = _msal_app().initiate_auth_code_flow(
        MS_SCOPES, redirect_uri=settings.MS_REDIRECT_URI
    )
    request.session["mate_auth_flow"] = flow
    return flow["auth_uri"]


def complete_login(request):
    """
    Handles the redirect back from Microsoft (the query string on
    request.GET). Returns (email, error) -- exactly one of the two is set.
    Pops the one-time flow state out of the session either way, so a
    callback URL can't be replayed to sign in twice off one flow.
    """
    flow = request.session.pop("mate_auth_flow", None)
    if not flow:
        return None, "No sign-in in progress (your session may have expired) -- please try signing in again."
    try:
        result = _msal_app().acquire_token_by_auth_code_flow(flow, request.GET.dict())
    except ValueError as e:
        # msal raises ValueError for a state/CSRF mismatch, or when the
        # query string itself carries an error from Microsoft (e.g. the
        # user clicked "Cancel" on the consent screen).
        return None, str(e)
    if "error" in result:
        return None, result.get("error_description", result["error"])
    claims = result.get("id_token_claims") or {}
    email = claims.get("email") or claims.get("preferred_username") or ""
    if not email_domain_allowed(email):
        domains = " or ".join(f"@{d}" for d in sorted(_allowed_domains()))
        return None, (
            f"Signed in as {email or 'an account'}, but only {domains} accounts "
            "can submit jobs to the cluster."
        )
    return email, None
