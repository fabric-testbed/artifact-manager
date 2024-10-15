import os

from django.shortcuts import render

from artifactmgr.apps.artifacts.views import list_object_paginator, ListObjectType
from artifactmgr.server.settings import API_DEBUG
from artifactmgr.utils.fabric_auth import get_api_user


def landing_page(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    message = None
    try:
        # author = AuthorViewSet.as_view({'get': 'retrieve'})(request=request, *args, **kwargs)
        # if author.data and author.status_code == status.HTTP_200_OK:
        #     author = json.loads(json.dumps(author.data))
        #     kwargs.update({'author_uuid': kwargs.get('uuid')})
        # else:
        #     message = {'status_code': author.status_code, 'detail': author.data.get('detail')}
        #     author = {}
        #     kwargs.update({'author_uuid': os.getenv('API_USER_ANON_UUID')})
        if api_user.is_authenticated:
            kwargs.update({'author_uuid': api_user.uuid})
        else:
            kwargs.update({'author_uuid': os.getenv('API_USER_ANON_UUID')})
        artifacts = list_object_paginator(request=request, object_type=ListObjectType.AUTHOR_BY_UUID, *args, **kwargs)
        if not message:
            message = artifacts.get('message', None)
    except Exception as exc:
        message = exc
        author = {}
        artifacts = {}
    return render(request,
                  'home.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifacts': artifacts.get('list_objects', {}),
                      'author': None,
                      'item_range': artifacts.get('item_range', None),
                      'message': message,
                      'next_page': artifacts.get('next_page', None),
                      'prev_page': artifacts.get('prev_page', None),
                      'search': artifacts.get('search', None),
                      'count': artifacts.get('count', None),
                      'debug': API_DEBUG
                  })
