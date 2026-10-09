"""Request identity and shared, per-artifact serializer visibility."""


def request_api_user(request, resolve):
    # Web views can wrap the same HttpRequest in several DRF Requests.
    request = getattr(request, '_request', request)
    if not hasattr(request, '_artifact_api_user'):
        request._artifact_api_user = resolve(request=request)
    return request._artifact_api_user


def artifact_visibility(artifact, context):
    """Cache author and project detail visibility once per artifact/serialization."""
    visibility = context.setdefault('artifact_visibility', {})
    if artifact.uuid not in visibility:
        api_user = context.get('api_user')
        is_author = bool(api_user and (not artifact.show_authors or not artifact.show_project)
                         and artifact.is_author(api_user.uuid))
        visibility[artifact.uuid] = (artifact.show_authors or is_author, artifact.show_project or is_author)
    return visibility[artifact.uuid]
