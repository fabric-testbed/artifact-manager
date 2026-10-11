from django.http import Http404, HttpResponse
from django.shortcuts import render

from artifactmgr.apps.artifacts.models import ArtifactAuthor
from artifactmgr.apps.artifacts.views import list_object_paginator, ListObjectType
from artifactmgr.server.settings import API_DEBUG
from artifactmgr.utils.api_logger import consoleLogger
from artifactmgr.utils.fabric_auth import get_api_user

# Served by Django rather than nginx so every run mode answers /robots.txt the same way. The
# artifact listing and detail pages stay crawlable; the API, admin and authentication paths and
# the create/update forms do not.
ROBOTS_TXT = '\n'.join([
    'User-agent: *',
    'Disallow: /api/',
    'Disallow: /admin/',
    'Disallow: /auth',
    'Disallow: /login',
    'Disallow: /logout',
    'Disallow: /artifacts/create/',
    'Disallow: /*/update',
]) + '\n'


def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type='text/plain')


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
    except Http404:
        raise
    except Exception:
        consoleLogger.exception('landing_page: unable to render the landing page for user %s', api_user.uuid)
        message = 'Unable to load this page; please retry.'
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
