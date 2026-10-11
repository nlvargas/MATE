"""
The frontend builds every backend URL from window.__MATE_CONFIG__.apiBase
(see frontend/src/api.js), which frontend/views.py computes per request.
Hardcoding "/dev" in the bundle made upload/run/sensitivity 404 on the
deployed custom domain, where the routes live at the root.
"""
import os
import sys

_CLIENT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CLIENT_DIR not in sys.path:
    sys.path.insert(0, _CLIENT_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

import django
django.setup()

from django.test import RequestFactory, override_settings

from frontend.views import _api_base


def _request(script_name=""):
    request = RequestFactory().get("/")
    request.META["SCRIPT_NAME"] = script_name
    return request


@override_settings(DEBUG=True)
def test_local_runserver_keeps_the_dev_prefix():
    assert _api_base(_request()) == "/dev"


@override_settings(DEBUG=False)
def test_custom_domain_has_no_prefix():
    assert _api_base(_request()) == ""


@override_settings(DEBUG=False)
def test_default_execute_api_url_uses_the_stage_name():
    assert _api_base(_request("/dev")) == "/dev"
