from django.shortcuts import render

from artifactmgr.apps.artifacts.models import ArtifactAuthor
from artifactmgr.apps.artifacts.views import list_object_paginator, ListObjectType
from artifactmgr.server.settings import API_DEBUG
from artifactmgr.utils.fabric_auth import get_api_user


def landing_page(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    message = None
    try:
        if api_user.is_authenticated:
            author = ArtifactAuthor.objects.filter(uuid=api_user.uuid).first()
            if author:
                kwargs.update({'uuid': author.uuid, 'author_uuid': author.uuid})
        artifacts = list_object_paginator(request=request, object_type=ListObjectType.AUTHOR_BY_UUID, *args, **kwargs)
        if not message:
            message = artifacts.get('message', None)
    except Exception as exc:
        message = exc
        artifacts = {}
    return render(request,
                  'home.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifacts': artifacts.get('list_objects', {}),
                      'item_range': artifacts.get('item_range', None),
                      'message': message,
                      'next_page': artifacts.get('next_page', None),
                      'prev_page': artifacts.get('prev_page', None),
                      'search': artifacts.get('search', None),
                      'count': artifacts.get('count', None),
                      'debug': API_DEBUG
                  })
