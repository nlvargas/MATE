from django.conf import settings
from django.http import HttpResponsePermanentRedirect
from django.http.request import split_domain_port, validate_host


class StripWwwMiddleware:
    """Sends www.mate.compile.cl to mate.compile.cl."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get("HTTP_HOST", "")
        if host.lower().startswith("www."):
            bare = host[4:]
            domain, _ = split_domain_port(bare)
            if domain and validate_host(domain, settings.ALLOWED_HOSTS):
                return HttpResponsePermanentRedirect(f"{request.scheme}://{bare}{request.get_full_path()}")
        return self.get_response(request)
