"""Request identity, crawler detection and shared, per-artifact serializer visibility."""

from django.conf import settings


def request_api_user(request, resolve):
    # Web views can wrap the same HttpRequest in several DRF Requests.
    request = getattr(request, '_request', request)
    if not hasattr(request, '_artifact_api_user'):
        request._artifact_api_user = resolve(request=request)
    return request._artifact_api_user


def is_crawler(request) -> bool:
    """True when the User-Agent carries a CRAWLER_USER_AGENT_MARKERS substring; memoised per request."""
    request = getattr(request, '_request', request)
    if not hasattr(request, '_artifact_is_crawler'):
        user_agent = request.META.get('HTTP_USER_AGENT', '').casefold()
        request._artifact_is_crawler = any(marker in user_agent for marker in settings.CRAWLER_USER_AGENT_MARKERS)
    return request._artifact_is_crawler


def artifact_visibility(artifact, context):
    """Cache author and project detail visibility once per artifact/serialization."""
    visibility = context.setdefault('artifact_visibility', {})
    if artifact.uuid not in visibility:
        api_user = context.get('api_user')
        is_author = bool(api_user and (not artifact.show_authors or not artifact.show_project)
                         and artifact.is_author(api_user.uuid))
        visibility[artifact.uuid] = (artifact.show_authors or is_author, artifact.show_project or is_author)
    return visibility[artifact.uuid]
