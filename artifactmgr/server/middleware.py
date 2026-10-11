"""Request-level gates that sit in front of Django's own URL routing."""

from django.conf import settings
from django.http import Http404

from artifactmgr.apps.artifacts.api.context import request_api_user
from artifactmgr.utils.fabric_auth import get_api_user


class AdminGateMiddleware:
    """
    Hide the Django admin unless DJANGO_ADMIN_ENABLED is on and the FABRIC user holds
    ARTIFACT_MANAGER_ADMINS_ROLE. 404 rather than 403 so the path does not advertise itself;
    Django's own superuser login still applies behind the gate.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/admin' or request.path.startswith('/admin/'):
            if not settings.DJANGO_ADMIN_ENABLED:
                raise Http404
            api_user = request_api_user(request, get_api_user)
            if not (api_user and api_user.is_artifact_manager_admin):
                raise Http404
        return self.get_response(request)
